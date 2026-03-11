"""
Endpoints para importação de notas fiscais via Email IMAP.
"""
import logging
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, status
from pydantic import BaseModel, Field, EmailStr

from app.dependencies import get_current_user, get_admin_db

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/email")


# ============================================
# SCHEMAS
# ============================================

class EmailConfigCreate(BaseModel):
    """Schema para criar/atualizar configuração de email."""
    tipo: str = Field("escritorio", description="'escritorio' ou 'empresa'")
    provedor: str = Field("imap_generico", description="'gmail', 'outlook', 'imap_generico'")
    email: EmailStr
    empresa_id: Optional[str] = None

    # IMAP
    imap_host: Optional[str] = None
    imap_port: int = 993
    imap_usuario: Optional[str] = None
    imap_senha: Optional[str] = None

    # OAuth
    oauth_access_token: Optional[str] = None
    oauth_refresh_token: Optional[str] = None
    oauth_token_expiry: Optional[str] = None

    pastas_monitoradas: Optional[List[str]] = None

    # Para update
    id: Optional[str] = None


class EmailConfigResponse(BaseModel):
    id: str
    tipo: str
    provedor: str
    email: str
    empresa_id: Optional[str] = None
    imap_host: Optional[str] = None
    imap_port: Optional[int] = None
    pastas_monitoradas: Optional[List[str]] = None
    ultima_sincronizacao: Optional[str] = None
    total_importadas: Optional[int] = 0
    ativo: bool = True


class SincronizacaoResponse(BaseModel):
    config_id: str
    emails_processados: int = 0
    xmls_encontrados: int = 0
    notas_importadas: int = 0
    notas_duplicadas: int = 0
    erros: int = 0
    detalhes_erros: list = []
    erro_geral: Optional[str] = None


# ============================================
# ENDPOINTS
# ============================================

@router.post(
    "/configurar",
    response_model=dict,
    summary="Salvar configuração de email",
)
async def configurar_email(
    dados: EmailConfigCreate,
    usuario: dict = Depends(get_current_user),
):
    """
    Salva ou atualiza configuração de email para importação de XMLs.

    Suporta Gmail, Outlook e servidores IMAP genéricos.
    """
    from app.services.email_import_service import email_import_service

    try:
        config = await email_import_service.salvar_configuracao(
            user_id=usuario["id"],
            dados=dados.model_dump(exclude_none=True),
        )
        return {
            "sucesso": True,
            "mensagem": "Configuração de email salva com sucesso",
            "config": config,
        }
    except Exception as e:
        logger.error(f"Erro ao salvar config email: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.get(
    "/configuracoes",
    response_model=List[EmailConfigResponse],
    summary="Listar configurações de email",
)
async def listar_configuracoes(
    usuario: dict = Depends(get_current_user),
):
    """Lista todas as configurações de email do usuário."""
    from app.services.email_import_service import email_import_service

    configs = await email_import_service.listar_configuracoes(usuario["id"])
    return configs


@router.post(
    "/sincronizar/{config_id}",
    response_model=SincronizacaoResponse,
    summary="Sincronizar emails (buscar XMLs)",
)
async def sincronizar_email(
    config_id: str,
    background_tasks: BackgroundTasks,
    usuario: dict = Depends(get_current_user),
):
    """
    Dispara sincronização de email para buscar XMLs fiscais.

    A sincronização roda em background e retorna o resumo quando concluída.
    """
    from app.services.email_import_service import email_import_service
    from app.db.supabase_client import get_supabase_admin

    db = get_supabase_admin()

    # Criar job de background
    job_data = {
        "user_id": usuario["id"],
        "type": "email_sync",
        "status": "processing",
        "result": {"config_id": config_id},
    }

    try:
        job_result = db.table("background_jobs").insert(job_data).execute()
        job_id = job_result.data[0]["id"] if job_result.data else None
    except Exception:
        job_id = None

    # Executar sincronização
    try:
        resumo = await email_import_service.sincronizar(
            config_id=config_id,
            user_id=usuario["id"],
        )

        # Atualizar job
        if job_id:
            db.table("background_jobs").update({
                "status": "completed",
                "result": resumo,
            }).eq("id", job_id).execute()

        return SincronizacaoResponse(**resumo)

    except Exception as e:
        logger.error(f"Erro na sincronização: {e}")
        if job_id:
            db.table("background_jobs").update({
                "status": "failed",
                "error": str(e),
            }).eq("id", job_id).execute()

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.delete(
    "/configuracoes/{config_id}",
    summary="Remover configuração de email",
)
async def remover_configuracao(
    config_id: str,
    usuario: dict = Depends(get_current_user),
):
    """Remove uma configuração de email."""
    from app.services.email_import_service import email_import_service

    removido = await email_import_service.remover_configuracao(
        config_id, usuario["id"]
    )
    if not removido:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Configuração não encontrada",
        )
    return {"sucesso": True, "mensagem": "Configuração removida"}


@router.get(
    "/logs",
    summary="Listar logs de importação",
)
async def listar_logs_importacao(
    fonte: Optional[str] = None,
    limite: int = 50,
    usuario: dict = Depends(get_current_user),
):
    """Lista logs de importação de notas (email, drive, manual)."""
    from app.db.supabase_client import get_supabase_admin

    db = get_supabase_admin()

    query = (
        db.table("log_importacao")
        .select("*")
        .eq("user_id", usuario["id"])
        .order("created_at", desc=True)
        .limit(limite)
    )

    if fonte:
        query = query.eq("fonte", fonte)

    result = query.execute()
    return result.data or []
