"""
Serviço de configuração de sincronização automática de notas.

Regras:
- Configuração global por contador (usuario).
- Configuração opcional por empresa (override).
- Plano admin pode forçar sincronização manual.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, time, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

TIPOS_VALIDOS = {"NFSE", "NFE", "NFCE", "CTE"}
TIPOS_PADRAO = ["NFSE", "NFE", "NFCE", "CTE"]
_FALLBACK_CONFIG = {
    "auto_sync_ativo": True,
    "intervalo_horas": 4,
    "prioridade_recente": True,
    "reparar_incompletas": True,
    "tipos_notas": TIPOS_PADRAO,
    "horario_inicio": "00:00:00",
    "horario_fim": "23:59:59",
}


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _schedule_tz_name() -> str:
    return str(os.getenv("SYNC_SCHEDULE_TZ", "America/Sao_Paulo")).strip() or "America/Sao_Paulo"


def _to_bool(value: Any, default: bool = True) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    txt = str(value).strip().lower()
    if txt in {"1", "true", "yes", "on", "sim"}:
        return True
    if txt in {"0", "false", "no", "off", "nao", "não"}:
        return False
    return default


def _to_intervalo_horas(value: Any, default: int = 4) -> int:
    try:
        n = int(value)
    except Exception:  # noqa: BLE001
        return default
    return max(1, min(24, n))


def _to_time_hhmmss(value: Any, default_value: str) -> str:
    if value is None:
        return default_value
    txt = str(value).strip()
    if not txt:
        return default_value

    parts = txt.split(":")
    if len(parts) not in {2, 3}:
        return default_value
    try:
        hh = int(parts[0])
        mm = int(parts[1])
        ss = int(parts[2]) if len(parts) == 3 else 0
    except Exception:  # noqa: BLE001
        return default_value
    if not (0 <= hh <= 23 and 0 <= mm <= 59 and 0 <= ss <= 59):
        return default_value
    return f"{hh:02d}:{mm:02d}:{ss:02d}"


def _to_tipos_notas(value: Any, default_value: Optional[List[str]] = None) -> List[str]:
    if default_value is None:
        default_value = TIPOS_PADRAO
    raw: List[str] = []
    if value is None:
        raw = list(default_value)
    elif isinstance(value, list):
        raw = [str(v).strip().upper() for v in value if str(v).strip()]
    else:
        raw = [str(value).strip().upper()]

    dedup: List[str] = []
    for item in raw:
        if item in TIPOS_VALIDOS and item not in dedup:
            dedup.append(item)
    return dedup or list(default_value)


def normalize_config_payload(
    payload: Dict[str, Any],
    include_uso_geral: bool = False,
) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    if "auto_sync_ativo" in payload:
        out["auto_sync_ativo"] = _to_bool(payload.get("auto_sync_ativo"), True)
    if "intervalo_horas" in payload:
        out["intervalo_horas"] = _to_intervalo_horas(payload.get("intervalo_horas"), 4)
    if "prioridade_recente" in payload:
        out["prioridade_recente"] = _to_bool(payload.get("prioridade_recente"), True)
    if "reparar_incompletas" in payload:
        out["reparar_incompletas"] = _to_bool(payload.get("reparar_incompletas"), True)
    if "tipos_notas" in payload:
        out["tipos_notas"] = _to_tipos_notas(payload.get("tipos_notas"), TIPOS_PADRAO)
    if "horario_inicio" in payload:
        out["horario_inicio"] = _to_time_hhmmss(payload.get("horario_inicio"), "00:00:00")
    if "horario_fim" in payload:
        out["horario_fim"] = _to_time_hhmmss(payload.get("horario_fim"), "23:59:59")
    if include_uso_geral and "usar_configuracao_contador" in payload:
        out["usar_configuracao_contador"] = _to_bool(payload.get("usar_configuracao_contador"), True)
    return out


def _normalize_row(row: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    src = row or {}
    return {
        "auto_sync_ativo": _to_bool(src.get("auto_sync_ativo"), True),
        "intervalo_horas": _to_intervalo_horas(src.get("intervalo_horas"), 4),
        "prioridade_recente": _to_bool(src.get("prioridade_recente"), True),
        "reparar_incompletas": _to_bool(src.get("reparar_incompletas"), True),
        "tipos_notas": _to_tipos_notas(src.get("tipos_notas"), TIPOS_PADRAO),
        "horario_inicio": _to_time_hhmmss(src.get("horario_inicio"), "00:00:00"),
        "horario_fim": _to_time_hhmmss(src.get("horario_fim"), "23:59:59"),
    }


def normalize_config_row(row: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    return _normalize_row(row)


def _hora_to_time(value: str, fallback: time) -> time:
    try:
        hh, mm, ss = [int(x) for x in value.split(":")]
        return time(hour=hh, minute=mm, second=ss)
    except Exception:  # noqa: BLE001
        return fallback


def _in_window(now_local: datetime, inicio: time, fim: time) -> bool:
    agora = now_local.time()
    if inicio <= fim:
        return inicio <= agora <= fim
    # Janela cruza meia-noite.
    return agora >= inicio or agora <= fim


def _next_window_start(now_local: datetime, inicio: time, fim: time) -> datetime:
    hoje_inicio = now_local.replace(hour=inicio.hour, minute=inicio.minute, second=inicio.second, microsecond=0)
    if inicio <= fim:
        if now_local <= hoje_inicio:
            return hoje_inicio
        return hoje_inicio + timedelta(days=1)

    # Janela cruzando meia-noite: fora da janela apenas no intervalo (fim, inicio).
    if fim < now_local.time() < inicio:
        return hoje_inicio
    return hoje_inicio + timedelta(days=1)


def evaluate_schedule_window(config: Dict[str, Any]) -> Dict[str, Any]:
    tz_name = _schedule_tz_name()
    try:
        from zoneinfo import ZoneInfo

        tzinfo = ZoneInfo(tz_name)
    except Exception:  # noqa: BLE001
        tzinfo = timezone.utc
        tz_name = "UTC"

    now_local = datetime.now(tzinfo)
    inicio = _hora_to_time(str(config.get("horario_inicio") or "00:00:00"), time(0, 0, 0))
    fim = _hora_to_time(str(config.get("horario_fim") or "23:59:59"), time(23, 59, 59))

    in_window = _in_window(now_local, inicio, fim)
    next_start_local = now_local if in_window else _next_window_start(now_local, inicio, fim)
    next_start_utc = next_start_local.astimezone(timezone.utc)

    return {
        "agora_na_janela": in_window,
        "proximo_inicio_janela_utc": next_start_utc.isoformat(),
        "timezone": tz_name,
    }


def usuario_eh_admin(db, usuario_id: str) -> bool:
    try:
        resp = (
            db.table("assinaturas")
            .select("id, planos!inner(nome)")
            .eq("usuario_id", usuario_id)
            .eq("status", "ativa")
            .order("data_fim", desc=True)
            .limit(5)
            .execute()
        )
        for assinatura in (resp.data or []):
            plano = assinatura.get("planos") or {}
            nome = str(plano.get("nome") or "").strip().lower()
            if nome == "admin":
                return True
    except Exception:  # noqa: BLE001
        logger.exception("Falha ao verificar plano admin do usuario_id=%s", usuario_id)
    return False


def _empresa_usuario_id(db, empresa_id: str) -> Optional[str]:
    try:
        resp = db.table("empresas").select("usuario_id").eq("id", empresa_id).limit(1).execute()
        if resp.data:
            return str(resp.data[0].get("usuario_id") or "") or None
    except Exception:  # noqa: BLE001
        logger.exception("Falha ao buscar usuario da empresa_id=%s", empresa_id)
    return None


def get_or_create_contador_config(db, usuario_id: str) -> Dict[str, Any]:
    try:
        resp = (
            db.table("sync_configuracoes_contador")
            .select("*")
            .eq("usuario_id", usuario_id)
            .limit(1)
            .execute()
        )
        if resp.data:
            return resp.data[0]

        payload = {"usuario_id": usuario_id, **_FALLBACK_CONFIG}
        db.table("sync_configuracoes_contador").insert(payload).execute()
        resp2 = (
            db.table("sync_configuracoes_contador")
            .select("*")
            .eq("usuario_id", usuario_id)
            .limit(1)
            .execute()
        )
        return (resp2.data or [payload])[0]
    except Exception:  # noqa: BLE001
        logger.exception("Falha ao obter/criar configuracao do contador usuario_id=%s", usuario_id)
        return {"usuario_id": usuario_id, **_FALLBACK_CONFIG}


def get_or_create_empresa_config(db, usuario_id: str, empresa_id: str) -> Dict[str, Any]:
    try:
        resp = (
            db.table("sync_configuracoes_empresa")
            .select("*")
            .eq("empresa_id", empresa_id)
            .limit(1)
            .execute()
        )
        if resp.data:
            return resp.data[0]

        payload = {
            "empresa_id": empresa_id,
            "usuario_id": usuario_id,
            "usar_configuracao_contador": True,
            **_FALLBACK_CONFIG,
        }
        db.table("sync_configuracoes_empresa").insert(payload).execute()
        resp2 = (
            db.table("sync_configuracoes_empresa")
            .select("*")
            .eq("empresa_id", empresa_id)
            .limit(1)
            .execute()
        )
        return (resp2.data or [payload])[0]
    except Exception:  # noqa: BLE001
        logger.exception("Falha ao obter/criar configuracao da empresa_id=%s", empresa_id)
        return {
            "empresa_id": empresa_id,
            "usuario_id": usuario_id,
            "usar_configuracao_contador": True,
            **_FALLBACK_CONFIG,
        }


def update_contador_config(db, usuario_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    clean = normalize_config_payload(payload)
    if not clean:
        return get_or_create_contador_config(db, usuario_id)
    db.table("sync_configuracoes_contador").update(clean).eq("usuario_id", usuario_id).execute()
    return get_or_create_contador_config(db, usuario_id)


def update_empresa_config(db, usuario_id: str, empresa_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    clean = normalize_config_payload(payload, include_uso_geral=True)
    if not clean:
        return get_or_create_empresa_config(db, usuario_id, empresa_id)
    clean["usuario_id"] = usuario_id
    db.table("sync_configuracoes_empresa").update(clean).eq("empresa_id", empresa_id).execute()
    return get_or_create_empresa_config(db, usuario_id, empresa_id)


def resolve_empresa_config(
    db,
    empresa_id: str,
    usuario_id: Optional[str] = None,
) -> Dict[str, Any]:
    usuario = usuario_id or _empresa_usuario_id(db, empresa_id)
    if not usuario:
        return {
            "configuracao_contador": _normalize_row(None),
            "configuracao_empresa": {
                "usar_configuracao_contador": True,
                **_normalize_row(None),
            },
            "configuracao_efetiva": _normalize_row(None),
        }

    contador_row = get_or_create_contador_config(db, usuario)
    empresa_row = get_or_create_empresa_config(db, usuario, empresa_id)

    contador_cfg = _normalize_row(contador_row)
    empresa_cfg_raw = _normalize_row(empresa_row)
    usar_contador = _to_bool(empresa_row.get("usar_configuracao_contador"), True)
    efetiva = contador_cfg if usar_contador else empresa_cfg_raw

    return {
        "configuracao_contador": contador_cfg,
        "configuracao_empresa": {
            "usar_configuracao_contador": usar_contador,
            **empresa_cfg_raw,
        },
        "configuracao_efetiva": efetiva,
    }


def normalize_tipo_nf_value(value: str) -> str:
    txt = str(value or "").strip().upper()
    if txt in {"NFE", "NFCE", "CTE", "NFSE"}:
        return txt
    if txt == "NFCE":
        return "NFCE"
    return txt
