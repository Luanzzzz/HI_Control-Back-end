"""
Endpoints para importação de notas fiscais via Google Drive.
"""
import logging
import os
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from app.dependencies import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/drive")


def _exigir_google_configurado() -> None:
    """
    Exige que Google OAuth esteja configurado.
    Levanta HTTP 503 com detalhe estruturado se não estiver.
    """
    client_id = os.getenv("GOOGLE_CLIENT_ID")
    redirect_uri = os.getenv("GOOGLE_REDIRECT_URI")
    if not client_id or not redirect_uri:
        msg = (
            "Google OAuth não configurado. Configure GOOGLE_CLIENT_ID e "
            "GOOGLE_REDIRECT_URI no .env. Veja .env.example ou documentação."
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"error": "google_not_configured", "message": msg},
        )


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
    pasta_raiz_export_id: Optional[str] = None
    pasta_raiz_export_nome: Optional[str] = None
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


class DriveExportMassRequest(BaseModel):
    empresa_ids: Optional[List[str]] = None
    filtros: Dict[str, Any] = {}


class DriveExportJobResponse(BaseModel):
    id: str
    status: str
    total_notas: int = 0
    notas_processadas: int = 0
    notas_exportadas: int = 0
    notas_duplicadas: int = 0
    notas_erro: int = 0
    progresso_percentual: float = 0
    mensagem: Optional[str] = None
    pasta_raiz_id: Optional[str] = None
    criado_em: Optional[str] = None
    atualizado_em: Optional[str] = None


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
    _exigir_google_configurado()
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
    _exigir_google_configurado()
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

        # Autoestrutura de pastas no Drive por cliente
        try:
            await google_drive_service.sincronizar_pastas_clientes(
                user_id=usuario["id"],
                config=config,
            )
        except Exception:
            logger.exception("Falha ao sincronizar pastas de clientes apos callback Google Drive")

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
    _exigir_google_configurado()
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
    "/pastas/sincronizar-clientes",
    summary="Criar/atualizar pastas de clientes no Drive",
)
async def sincronizar_pastas_clientes_drive(
    empresa_ids: Optional[List[str]] = None,
    usuario: dict = Depends(get_current_user),
):
    _exigir_google_configurado()
    from app.services.google_drive_service import google_drive_service

    try:
        resultado = await google_drive_service.sincronizar_pastas_clientes(
            user_id=usuario["id"],
            empresa_ids=empresa_ids,
        )
        return {
            "sucesso": True,
            "mensagem": "Pastas sincronizadas com sucesso",
            **resultado,
        }
    except Exception as e:
        logger.error(f"Erro ao sincronizar pastas de clientes no Drive: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.post(
    "/exportacoes/xmls/iniciar",
    response_model=DriveExportJobResponse,
    summary="Iniciar exportacao em massa de XML para Google Drive",
)
async def iniciar_exportacao_massa_xml(
    payload: DriveExportMassRequest,
    usuario: dict = Depends(get_current_user),
):
    _exigir_google_configurado()
    from app.services.google_drive_service import google_drive_service

    try:
        job = await google_drive_service.iniciar_exportacao_xml_massa(
            user_id=usuario["id"],
            empresa_ids=payload.empresa_ids,
            filtros=payload.filtros or {},
        )
        return DriveExportJobResponse(
            id=str(job.get("id")),
            status=str(job.get("status") or "pendente"),
            total_notas=int(job.get("total_notas") or 0),
            notas_processadas=int(job.get("notas_processadas") or 0),
            notas_exportadas=int(job.get("notas_exportadas") or 0),
            notas_duplicadas=int(job.get("notas_duplicadas") or 0),
            notas_erro=int(job.get("notas_erro") or 0),
            progresso_percentual=float(job.get("progresso_percentual") or 0),
            mensagem=job.get("mensagem"),
            pasta_raiz_id=job.get("pasta_raiz_id"),
            criado_em=job.get("created_at"),
            atualizado_em=job.get("updated_at"),
        )
    except Exception as e:
        logger.error(f"Erro ao iniciar exportacao em massa para Drive: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.get(
    "/exportacoes/xmls/{job_id}",
    response_model=DriveExportJobResponse,
    summary="Consultar status da exportacao em massa de XML",
)
async def consultar_exportacao_massa_xml(
    job_id: str,
    usuario: dict = Depends(get_current_user),
):
    from app.services.google_drive_service import google_drive_service

    try:
        job = await google_drive_service.obter_status_exportacao(
            job_id=job_id,
            user_id=usuario["id"],
        )
        return DriveExportJobResponse(
            id=str(job.get("id")),
            status=str(job.get("status") or "pendente"),
            total_notas=int(job.get("total_notas") or 0),
            notas_processadas=int(job.get("notas_processadas") or 0),
            notas_exportadas=int(job.get("notas_exportadas") or 0),
            notas_duplicadas=int(job.get("notas_duplicadas") or 0),
            notas_erro=int(job.get("notas_erro") or 0),
            progresso_percentual=float(job.get("progresso_percentual") or 0),
            mensagem=job.get("mensagem"),
            pasta_raiz_id=job.get("pasta_raiz_id"),
            criado_em=job.get("created_at"),
            atualizado_em=job.get("updated_at"),
        )
    except Exception as e:
        logger.error(f"Erro ao consultar job de exportacao Drive: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )


@router.get(
    "/exportacoes/xmls",
    summary="Listar exportacoes em massa de XML",
)
async def listar_exportacoes_massa_xml(
    limite: int = 20,
    usuario: dict = Depends(get_current_user),
):
    from app.services.google_drive_service import google_drive_service

    jobs = await google_drive_service.listar_exportacoes(
        user_id=usuario["id"],
        limite=limite,
    )
    return {"jobs": jobs}


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
    _exigir_google_configurado()
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
