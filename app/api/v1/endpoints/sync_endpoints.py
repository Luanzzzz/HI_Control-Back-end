"""
Endpoints de controle da sincronizacao SEFAZ.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, List

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from supabase import Client

from app.db.supabase_client import get_supabase_admin
from app.dependencies import get_admin_db, get_current_user
from app.services.captura_sefaz_service import captura_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/sync", tags=["Sync SEFAZ"])
_SYNC_PROGRESS_FIELDS = {
    "inicio_sync_at",
    "etapa_atual",
    "mensagem_progresso",
    "progresso_percentual",
    "notas_processadas_parcial",
    "notas_estimadas_total",
    "tempo_restante_estimado_segundos",
}


async def _validar_empresa_usuario(db: Client, empresa_id: str, usuario_id: str) -> None:
    resp = (
        db.table("empresas")
        .select("id")
        .eq("id", empresa_id)
        .eq("usuario_id", usuario_id)
        .eq("ativa", True)
        .limit(1)
        .execute()
    )
    if not resp.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Empresa nao encontrada ou sem permissao de acesso",
        )


def _prioridade_recente_habilitada() -> bool:
    valor = os.getenv("NFSE_ADN_PRIORIZAR_RECENTES", "true").strip().lower()
    return valor not in {"0", "false", "no", "off"}


def _obter_estado_prioridade_recente(db: Client, empresa_id: str) -> Dict[str, bool]:
    if not _prioridade_recente_habilitada():
        return {
            "prioridade_recente_ativa": False,
            "prioridade_recente_concluida": False,
        }

    try:
        resp = (
            db.table("credenciais_nfse")
            .select("token, usuario, ativo")
            .eq("empresa_id", empresa_id)
            .eq("ativo", True)
            .limit(20)
            .execute()
        )
        credenciais = resp.data or []
        if not credenciais:
            return {
                "prioridade_recente_ativa": False,
                "prioridade_recente_concluida": False,
            }

        auto = None
        for cred in credenciais:
            token = str(cred.get("token") or "").strip()
            usuario = str(cred.get("usuario") or "").strip().upper()
            if token.upper().startswith("AUTO_CERT_A1") or usuario == "AUTO_CERT_A1":
                auto = cred
                break

        if not auto:
            return {
                "prioridade_recente_ativa": False,
                "prioridade_recente_concluida": False,
            }

        token_upper = str(auto.get("token") or "").strip().upper()
        concluida = "HOTDONE:1" in token_upper
        ativa = not concluida
        return {
            "prioridade_recente_ativa": ativa,
            "prioridade_recente_concluida": concluida,
        }
    except Exception:  # noqa: BLE001
        logger.exception("Falha ao obter estado da prioridade recente da empresa_id=%s", empresa_id)
        return {
            "prioridade_recente_ativa": False,
            "prioridade_recente_concluida": False,
        }


def _upsert_sync_empresa_seguro(db: Client, payload: Dict[str, Any]) -> None:
    try:
        db.table("sync_empresas").upsert(payload, on_conflict="empresa_id").execute()
        return
    except Exception:  # noqa: BLE001
        fallback = {k: v for k, v in payload.items() if k not in _SYNC_PROGRESS_FIELDS}
        db.table("sync_empresas").upsert(fallback, on_conflict="empresa_id").execute()


def _executar_sync_forcada(
    empresa_id: str,
    prioridade_recente: bool = True,
    reparar_incompletas: bool = True,
) -> None:
    db = get_supabase_admin()
    try:
        now_iso = datetime.now(timezone.utc).isoformat()
        _upsert_sync_empresa_seguro(
            db,
            {
                "empresa_id": empresa_id,
                "status": "sincronizando",
                "erro_mensagem": None,
                "inicio_sync_at": now_iso,
                "etapa_atual": "fila",
                "mensagem_progresso": "Sincronizacao enfileirada...",
                "progresso_percentual": 1.0,
                "notas_processadas_parcial": 0,
                "notas_estimadas_total": None,
                "tempo_restante_estimado_segundos": None,
            },
        )
        logger.info("Executando sincronizacao forcada para empresa_id=%s", empresa_id)
        captura_service.sincronizar_empresa(
            empresa_id,
            db,
            reparar_incompletas=reparar_incompletas,
            reset_cursor_recente=prioridade_recente,
        )
    except Exception:  # noqa: BLE001
        logger.exception("Falha em sincronizacao forcada da empresa_id=%s", empresa_id)
        try:
            db.table("sync_empresas").update(
                {
                    "status": "erro",
                    "erro_mensagem": "Falha interna ao executar sincronizacao forcada",
                }
            ).eq("empresa_id", empresa_id).execute()
        except Exception:  # noqa: BLE001
            logger.exception("Falha ao atualizar status de erro da sync forcada empresa_id=%s", empresa_id)


@router.get("/empresas/{empresa_id}/status")
async def get_sync_status(
    empresa_id: str,
    usuario: Dict[str, Any] = Depends(get_current_user),
    db: Client = Depends(get_admin_db),
):
    await _validar_empresa_usuario(db, empresa_id, usuario["id"])

    resp = db.table("sync_empresas").select("*").eq("empresa_id", empresa_id).limit(1).execute()
    row = resp.data[0] if resp.data else None

    if row is None:
        db.table("sync_empresas").insert({"empresa_id": empresa_id}).execute()
        resp = db.table("sync_empresas").select("*").eq("empresa_id", empresa_id).limit(1).execute()
        row = (resp.data or [{}])[0]
    estado_prioridade = _obter_estado_prioridade_recente(db, empresa_id)
    estimadas = row.get("notas_estimadas_total")
    processadas = row.get("notas_processadas_parcial")
    try:
        estimadas_int = int(estimadas) if estimadas is not None else None
    except Exception:  # noqa: BLE001
        estimadas_int = None
    try:
        processadas_int = int(processadas) if processadas is not None else 0
    except Exception:  # noqa: BLE001
        processadas_int = 0
    restantes_int = None
    if estimadas_int is not None:
        restantes_int = max(0, estimadas_int - processadas_int)

    return {
        "empresa_id": empresa_id,
        "status": row.get("status", "pendente"),
        "ultima_sync": row.get("ultima_sync"),
        "proximo_sync": row.get("proximo_sync"),
        "total_notas_capturadas": row.get("total_notas_capturadas", 0),
        "notas_capturadas_ultima_sync": row.get("notas_capturadas_ultima_sync", 0),
        "erro_mensagem": row.get("erro_mensagem"),
        "ultimo_nsu": row.get("ultimo_nsu", 0),
        "inicio_sync_at": row.get("inicio_sync_at"),
        "etapa_atual": row.get("etapa_atual"),
        "mensagem_progresso": row.get("mensagem_progresso"),
        "progresso_percentual": float(row.get("progresso_percentual") or 0),
        "notas_processadas_parcial": processadas_int,
        "notas_estimadas_total": estimadas_int,
        "notas_restantes_estimadas": restantes_int,
        "tempo_restante_estimado_segundos": row.get("tempo_restante_estimado_segundos"),
        "prioridade_recente_ativa": estado_prioridade["prioridade_recente_ativa"],
        "prioridade_recente_concluida": estado_prioridade["prioridade_recente_concluida"],
    }


@router.post("/empresas/{empresa_id}/forcar")
async def force_sync_empresa(
    empresa_id: str,
    background_tasks: BackgroundTasks,
    prioridade_recente: bool = True,
    reparar_incompletas: bool = True,
    usuario: Dict[str, Any] = Depends(get_current_user),
    db: Client = Depends(get_admin_db),
):
    await _validar_empresa_usuario(db, empresa_id, usuario["id"])

    now_iso = datetime.now(timezone.utc).isoformat()
    _upsert_sync_empresa_seguro(
        db,
        {
            "empresa_id": empresa_id,
            "proximo_sync": now_iso,
            "status": "sincronizando",
            "erro_mensagem": None,
            "inicio_sync_at": now_iso,
            "etapa_atual": "fila",
            "mensagem_progresso": "Sincronizacao enfileirada...",
            "progresso_percentual": 1.0,
            "notas_processadas_parcial": 0,
            "notas_estimadas_total": None,
            "tempo_restante_estimado_segundos": None,
        },
    )

    background_tasks.add_task(
        _executar_sync_forcada,
        empresa_id,
        prioridade_recente,
        reparar_incompletas,
    )
    return {
        "mensagem": "Sincronizacao agendada",
        "empresa_id": empresa_id,
        "prioridade_recente": prioridade_recente,
        "reparo_incompletas": reparar_incompletas,
    }


@router.get("/empresas/{empresa_id}/historico")
async def get_sync_historico(
    empresa_id: str,
    usuario: Dict[str, Any] = Depends(get_current_user),
    db: Client = Depends(get_admin_db),
) -> List[Dict[str, Any]]:
    await _validar_empresa_usuario(db, empresa_id, usuario["id"])

    resp = (
        db.table("sync_log")
        .select("iniciado_em, status, notas_novas, duracao_ms, erro_detalhes")
        .eq("empresa_id", empresa_id)
        .order("iniciado_em", desc=True)
        .limit(20)
        .execute()
    )
    return resp.data or []
