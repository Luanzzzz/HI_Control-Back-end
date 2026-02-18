"""
Endpoints de controle da sincronizacao SEFAZ.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from supabase import Client

from app.db.supabase_client import get_supabase_admin
from app.dependencies import get_admin_db, get_current_user
from app.services.captura_sefaz_service import captura_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/sync", tags=["Sync SEFAZ"])


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


def _executar_sync_forcada(empresa_id: str) -> None:
    db = get_supabase_admin()
    try:
        logger.info("Executando sincronizacao forcada para empresa_id=%s", empresa_id)
        captura_service.sincronizar_empresa(empresa_id, db)
    except Exception:  # noqa: BLE001
        logger.exception("Falha em sincronizacao forcada da empresa_id=%s", empresa_id)


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

    return {
        "empresa_id": empresa_id,
        "status": row.get("status", "pendente"),
        "ultima_sync": row.get("ultima_sync"),
        "proximo_sync": row.get("proximo_sync"),
        "total_notas_capturadas": row.get("total_notas_capturadas", 0),
        "notas_capturadas_ultima_sync": row.get("notas_capturadas_ultima_sync", 0),
        "erro_mensagem": row.get("erro_mensagem"),
        "ultimo_nsu": row.get("ultimo_nsu", 0),
    }


@router.post("/empresas/{empresa_id}/forcar")
async def force_sync_empresa(
    empresa_id: str,
    background_tasks: BackgroundTasks,
    usuario: Dict[str, Any] = Depends(get_current_user),
    db: Client = Depends(get_admin_db),
):
    await _validar_empresa_usuario(db, empresa_id, usuario["id"])

    now_iso = datetime.now(timezone.utc).isoformat()
    db.table("sync_empresas").upsert(
        {
            "empresa_id": empresa_id,
            "proximo_sync": now_iso,
            "status": "pendente",
            "erro_mensagem": None,
        },
        on_conflict="empresa_id",
    ).execute()

    background_tasks.add_task(_executar_sync_forcada, empresa_id)
    return {
        "mensagem": "Sincronizacao agendada",
        "empresa_id": empresa_id,
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

