"""
Worker de sincronizacao do bot de captura SEFAZ.
"""
from __future__ import annotations

import logging
import threading
from datetime import datetime, timedelta, timezone
from typing import Optional

from app.services.captura_sefaz_service import captura_service
from app.services import sync_config_service

logger = logging.getLogger(__name__)

_scheduler = None
_worker_thread: Optional[threading.Thread] = None
_lock = threading.Lock()
_worker_db = None


def _get_worker_db():
    """Cria cliente Supabase próprio do worker (independente do FastAPI)."""
    global _worker_db
    if _worker_db is None:
        from supabase import create_client
        from app.core.config import settings

        _worker_db = create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_KEY)
    return _worker_db


def run_sync_cycle(db=None) -> None:
    """Executa um ciclo: pega empresas vencidas e sincroniza (max 10)."""
    if db is None:
        db = _get_worker_db()
    now_iso = datetime.now(timezone.utc).isoformat()

    try:
        response = (
            db.table("sync_empresas")
            .select("empresa_id, status, proximo_sync")
            .lte("proximo_sync", now_iso)
            .order("proximo_sync", desc=False)
            .limit(100)
            .execute()
        )
        rows = response.data or []
    except Exception as exc:  # noqa: BLE001
        logger.error("Falha ao buscar empresas para sync: %s", exc)
        return

    elegiveis = [r for r in rows if r.get("status") not in {"sincronizando", "sem_certificado"}][:10]
    if not elegiveis:
        logger.info("Sync cycle: nenhuma empresa elegivel")
        return

    empresa_ids = [r.get("empresa_id") for r in elegiveis if r.get("empresa_id")]
    empresa_usuario_map = {}
    if empresa_ids:
        try:
            empresa_resp = db.table("empresas").select("id, usuario_id").in_("id", empresa_ids).execute()
            empresa_usuario_map = {
                str(x.get("id")): str(x.get("usuario_id") or "")
                for x in (empresa_resp.data or [])
                if x.get("id")
            }
        except Exception as exc:  # noqa: BLE001
            logger.warning("Falha ao carregar empresas para configuracao de sync: %s", exc)

    logger.info("Sync cycle iniciado: %s empresas elegiveis", len(elegiveis))
    for row in elegiveis:
        empresa_id = row.get("empresa_id")
        if not empresa_id:
            continue

        try:
            usuario_id = empresa_usuario_map.get(str(empresa_id))
            resolved = sync_config_service.resolve_empresa_config(
                db=db,
                empresa_id=str(empresa_id),
                usuario_id=usuario_id,
            )
            cfg = resolved.get("configuracao_efetiva") or {}
            janela = sync_config_service.evaluate_schedule_window(cfg)

            if not cfg.get("auto_sync_ativo", True):
                db.table("sync_empresas").update(
                    {
                        "status": "pendente",
                        "erro_mensagem": "Sincronizacao automatica desativada na configuracao.",
                        "proximo_sync": (datetime.now(timezone.utc) + timedelta(hours=12)).isoformat(),
                    }
                ).eq("empresa_id", empresa_id).execute()
                continue

            if not janela.get("agora_na_janela", True):
                db.table("sync_empresas").update(
                    {
                        "status": "pendente",
                        "erro_mensagem": None,
                        "proximo_sync": janela.get("proximo_inicio_janela_utc"),
                    }
                ).eq("empresa_id", empresa_id).execute()
                continue

            db.table("sync_empresas").update({"status": "sincronizando", "erro_mensagem": None}).eq(
                "empresa_id", empresa_id
            ).execute()

            resultado = captura_service.sincronizar_empresa(
                empresa_id,
                db,
                reparar_incompletas=bool(cfg.get("reparar_incompletas", True)),
                reset_cursor_recente=bool(cfg.get("prioridade_recente", False)),
                intervalo_horas=int(cfg.get("intervalo_horas") or 4),
                tipos_permitidos=list(cfg.get("tipos_notas") or []),
            )
            status_final = resultado.get("status", "erro")

            payload = {"status": status_final}
            if resultado.get("erro_mensagem") is not None:
                payload["erro_mensagem"] = resultado.get("erro_mensagem")
            db.table("sync_empresas").update(payload).eq("empresa_id", empresa_id).execute()

        except Exception as exc:  # noqa: BLE001
            logger.exception("Falha ao sincronizar empresa_id=%s", empresa_id)
            try:
                db.table("sync_empresas").update(
                    {
                        "status": "erro",
                        "erro_mensagem": f"Erro no worker: {exc}",
                    }
                ).eq("empresa_id", empresa_id).execute()
            except Exception:  # noqa: BLE001
                logger.exception("Falha ao persistir erro do worker para empresa_id=%s", empresa_id)


def _scheduler_runner() -> None:
    global _scheduler
    try:
        from apscheduler.schedulers.blocking import BlockingScheduler
    except ImportError:
        logger.warning("APScheduler nao instalado. Worker SEFAZ nao sera iniciado.")
        return

    _scheduler = BlockingScheduler(timezone="UTC")
    _scheduler.add_job(
        run_sync_cycle,
        "interval",
        minutes=30,
        id="sefaz_sync_cycle",
        replace_existing=True,
        max_instances=1,
    )

    # Primeira execucao imediata para empresas novas (proximo_sync = NOW()).
    run_sync_cycle()
    _scheduler.start()


def start_worker() -> None:
    """Inicia o scheduler em thread separada sem bloquear o servidor HTTP."""
    global _worker_thread
    with _lock:
        if _worker_thread and _worker_thread.is_alive():
            return

        _worker_thread = threading.Thread(target=_scheduler_runner, name="sefaz-sync-worker", daemon=True)
        _worker_thread.start()
        logger.info("Worker de captura SEFAZ iniciado — ciclo a cada 30min")


def stop_worker() -> None:
    """Encerra scheduler/thread do worker."""
    global _scheduler, _worker_thread
    with _lock:
        if _scheduler:
            try:
                _scheduler.shutdown(wait=False)
            except Exception:  # noqa: BLE001
                pass
            _scheduler = None

        if _worker_thread and _worker_thread.is_alive():
            _worker_thread.join(timeout=2)
        _worker_thread = None
