"""
Endpoints para buscar notas diretamente do Google Drive.

Lê XMLs da pasta configurada e retorna dados parseados.
NÃO salva no banco - apenas leitura direta do Drive.
"""
import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel

from app.dependencies import get_current_user
from app.db.supabase_client import get_supabase_admin
from app.services.google_drive_service import google_drive_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/notas", tags=["Notas - Drive"])


class NotaDriveResponse(BaseModel):
    """Nota fiscal lida diretamente do Drive (não salva no banco)."""
    chave_acesso: Optional[str] = None
    numero: str
    serie: Optional[str] = None
    tipo: str
    data_emissao: Optional[str] = None
    valor_total: float = 0.0
    cnpj_emitente: Optional[str] = None
    nome_emitente: Optional[str] = None
    cnpj_destinatario: Optional[str] = None
    nome_destinatario: Optional[str] = None
    situacao: Optional[str] = None
    arquivo_nome: str
    drive_file_id: str


class NotasDriveListResponse(BaseModel):
    """Resposta da listagem de notas do Drive."""
    success: bool
    total: int
    notas: List[NotaDriveResponse]
    pasta_id: Optional[str] = None
    pasta_nome: Optional[str] = None
    message: Optional[str] = None


@router.get(
    "/drive/{empresa_id}",
    response_model=NotasDriveListResponse,
    summary="Buscar notas diretamente do Google Drive",
)
async def buscar_notas_drive(
    empresa_id: str,
    limite: int = Query(100, ge=1, le=500, description="Limite de notas"),
    usuario: dict = Depends(get_current_user),
):
    """
    Busca XMLs de notas fiscais diretamente do Google Drive.

    NÃO salva no banco - apenas lê e parseia os XMLs.

    Requer configuração de Drive ativa para a empresa.
    """
    user_id = usuario.get("id")
    db = get_supabase_admin()

    # 1. Verificar se empresa pertence ao usuário
    empresa_check = db.table("empresas")\
        .select("id, razao_social")\
        .eq("id", empresa_id)\
        .eq("usuario_id", user_id)\
        .eq("ativa", True)\
        .maybe_single()\
        .execute()

    if not empresa_check.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Empresa não encontrada"
        )

    # 2. Buscar configuração do Drive para esta empresa
    drive_config = db.table("configuracoes_drive")\
        .select("*")\
        .eq("empresa_id", empresa_id)\
        .eq("ativo", True)\
        .limit(1)\
        .execute()

    if not drive_config.data:
        return NotasDriveListResponse(
            success=True,
            total=0,
            notas=[],
            message="Google Drive não configurado para esta empresa"
        )

    config = drive_config.data[0]
    pasta_id = config.get("pasta_id")

    if not pasta_id:
        return NotasDriveListResponse(
            success=True,
            total=0,
            notas=[],
            message="Pasta do Drive não configurada"
        )

    # 3. Listar e baixar XMLs do Drive
    try:
        notas = await google_drive_service.listar_e_parsear_xmls(
            config=config,
            limite=limite
        )

        return NotasDriveListResponse(
            success=True,
            total=len(notas),
            notas=[NotaDriveResponse(**n) for n in notas],
            pasta_id=pasta_id,
            pasta_nome=config.get("pasta_nome")
        )

    except Exception as e:
        logger.error(f"Erro ao buscar notas do Drive: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erro ao buscar notas do Drive: {str(e)}"
        )


@router.post(
    "/drive/{empresa_id}/sincronizar",
    summary="Forçar sincronização do Drive",
)
async def forcar_sincronizacao_drive(
    empresa_id: str,
    usuario: dict = Depends(get_current_user),
):
    """
    Força sincronização do Drive (dispara importação).

    Importa XMLs do Drive para o banco de dados.
    """
    user_id = usuario.get("id")
    db = get_supabase_admin()

    # Buscar config_id
    drive_config = db.table("configuracoes_drive")\
        .select("id")\
        .eq("empresa_id", empresa_id)\
        .eq("ativo", True)\
        .limit(1)\
        .execute()

    if not drive_config.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Google Drive não configurado para esta empresa"
        )

    config_id = drive_config.data[0]["id"]

    try:
        resultado = await google_drive_service.sincronizar(
            config_id=config_id,
            user_id=user_id
        )

        return {
            "success": True,
            "message": "Sincronização concluída",
            **resultado
        }

    except Exception as e:
        logger.error(f"Erro ao sincronizar Drive: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erro ao sincronizar: {str(e)}"
        )
