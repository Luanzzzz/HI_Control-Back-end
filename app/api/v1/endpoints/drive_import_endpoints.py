"""
Endpoints para importação de notas fiscais via Google Drive.
"""
import logging
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.dependencies import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/drive")


# ============================================
# SCHEMAS
# ============================================

class DriveConfigCreate(BaseModel):
    empresa_id: Optional[str] = None
    pasta_id: Optional[str] = None
    pasta_nome: Optional[str] = None
    access_token: Optional[str] = None
    refresh_token: Optional[str] = None
    id: Optional[str] = None


class DriveConfigResponse(BaseModel):
    id: str
    provedor: str = "google_drive"
    empresa_id: Optional[str] = None
    pasta_id: Optional[str] = None
    pasta_nome: Optional[str] = None
    ultima_sincronizacao: Optional[str] = None
    total_importadas: Optional[int] = 0
    ativo: bool = True


class DriveSyncResponse(BaseModel):
    config_id: str
    arquivos_encontrados: int = 0
    notas_importadas: int = 0
    notas_duplicadas: int = 0
    erros: int = 0
    detalhes_erros: list = []
    erro_geral: Optional[str] = None


# ============================================
# ENDPOINTS
# ============================================

@router.get(
    "/auth/url",
    summary="Gerar URL de autorização Google",
)
async def gerar_url_auth(
    usuario: dict = Depends(get_current_user),
):
    """Gera a URL para o usuário autorizar acesso ao Google Drive."""
    from app.services.google_drive_service import google_drive_service

    try:
        url = google_drive_service.gerar_url_autorizacao(
            state=usuario["id"]
        )
        return {"url": url}
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.post(
    "/auth/callback",
    summary="Processar callback OAuth Google",
)
async def callback_oauth(
    code: str,
    state: Optional[str] = None,
    usuario: dict = Depends(get_current_user),
):
    """
    Processa o callback do OAuth2 do Google.
    Troca o authorization code por tokens.
    """
    from app.services.google_drive_service import google_drive_service

    try:
        tokens = await google_drive_service.processar_callback(
            code=code,
            user_id=usuario["id"],
        )

        # Salvar configuração com tokens
        config = await google_drive_service.salvar_configuracao(
            user_id=usuario["id"],
            dados={
                "access_token": tokens["access_token"],
                "refresh_token": tokens.get("refresh_token"),
            },
        )

        return {
            "sucesso": True,
            "mensagem": "Google Drive autorizado com sucesso",
            "config_id": config.get("id"),
        }
    except Exception as e:
        logger.error(f"Erro no callback OAuth: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.get(
    "/configuracoes",
    response_model=List[DriveConfigResponse],
    summary="Listar configurações de Drive",
)
async def listar_configuracoes(
    usuario: dict = Depends(get_current_user),
):
    from app.services.google_drive_service import google_drive_service
    configs = await google_drive_service.listar_configuracoes(usuario["id"])
    return configs


@router.get(
    "/pastas/{config_id}",
    summary="Listar pastas do Google Drive",
)
async def listar_pastas(
    config_id: str,
    usuario: dict = Depends(get_current_user),
):
    """Lista pastas do Google Drive para seleção."""
    from app.services.google_drive_service import google_drive_service

    try:
        pastas = await google_drive_service.listar_pastas(
            config_id, usuario["id"]
        )
        return {"pastas": pastas}
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.post(
    "/configurar",
    summary="Salvar configuração de pasta",
)
async def configurar_drive(
    dados: DriveConfigCreate,
    usuario: dict = Depends(get_current_user),
):
    """Salva a configuração de pasta a ser monitorada."""
    from app.services.google_drive_service import google_drive_service

    try:
        config = await google_drive_service.salvar_configuracao(
            user_id=usuario["id"],
            dados=dados.model_dump(exclude_none=True),
        )
        return {
            "sucesso": True,
            "mensagem": "Configuração salva",
            "config": config,
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.post(
    "/sincronizar/{config_id}",
    response_model=DriveSyncResponse,
    summary="Sincronizar Google Drive",
)
async def sincronizar_drive(
    config_id: str,
    usuario: dict = Depends(get_current_user),
):
    """Dispara sincronização do Google Drive - busca XMLs na pasta."""
    from app.services.google_drive_service import google_drive_service

    try:
        resumo = await google_drive_service.sincronizar(
            config_id=config_id,
            user_id=usuario["id"],
        )
        return DriveSyncResponse(**resumo)
    except Exception as e:
        logger.error(f"Erro na sincronização Drive: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.delete(
    "/configuracoes/{config_id}",
    summary="Remover configuração de Drive",
)
async def remover_configuracao(
    config_id: str,
    usuario: dict = Depends(get_current_user),
):
    from app.services.google_drive_service import google_drive_service

    removido = await google_drive_service.remover_configuracao(
        config_id, usuario["id"]
    )
    if not removido:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Configuração não encontrada",
        )
    return {"sucesso": True, "mensagem": "Configuração removida"}
