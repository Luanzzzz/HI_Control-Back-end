"""
Endpoints REST para busca e gestão de NFS-e (Nota Fiscal de Serviço Eletrônica).

Funcionalidades:
- Buscar NFS-e de uma empresa via API municipal
- Listar municípios suportados
- Gerenciar credenciais de acesso às APIs municipais
- Testar conexão com API municipal

Diferença para NF-e:
- NF-e = Estadual (SEFAZ) - Produtos
- NFS-e = Municipal (Prefeitura) - Serviços
"""
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from datetime import date, timedelta
from typing import Optional
import logging

from app.dependencies import get_current_user, get_admin_db, verificar_acesso_empresa
from app.services.nfse.nfse_service import nfse_service
from app.services.nfse.base_adapter import (
    NFSeException,
    NFSeAuthException,
    NFSeSearchException,
    NFSeConfigException,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/nfse", tags=["NFS-e - Notas de Serviço"])


# ============================================
# SCHEMAS DE REQUEST/RESPONSE
# ============================================

class BuscarNFSeRequest(BaseModel):
    """Schema para requisição de busca de NFS-e."""
    data_inicio: Optional[date] = Field(
        None,
        description="Data inicial da busca (padrão: 30 dias atrás)",
        examples=["2026-01-01"],
    )
    data_fim: Optional[date] = Field(
        None,
        description="Data final da busca (padrão: hoje)",
        examples=["2026-02-09"],
    )


class SalvarCredenciaisRequest(BaseModel):
    """Schema para salvar credenciais NFS-e."""
    municipio_codigo: str = Field(
        ...,
        description="Código IBGE do município (7 dígitos)",
        examples=["3106200"],
        min_length=7,
        max_length=7,
    )
    usuario: str = Field(
        ...,
        description="Usuário da API municipal",
        min_length=1,
    )
    senha: str = Field(
        ...,
        description="Senha da API municipal",
        min_length=1,
    )
    cnpj: Optional[str] = Field(
        None,
        description="CNPJ (se necessário pela API)",
    )
    token: Optional[str] = Field(
        None,
        description="Token de acesso (se aplicável)",
    )


# ============================================
# ENDPOINTS DE CONSULTA
# ============================================

@router.post(
    "/empresas/{empresa_id}/buscar",
    summary="Buscar NFS-e de uma empresa via API municipal",
    description="""
    Busca Notas Fiscais de Serviço (NFS-e) de uma empresa através da API municipal.

    **Fluxo:**
    1. Identifica o município da empresa
    2. Seleciona o sistema correto (BH, SP ou Sistema Nacional)
    3. Autentica na API municipal
    4. Busca notas emitidas pelo CNPJ no período
    5. Salva as notas no banco de dados Hi-Control

    **Pré-requisitos:**
    - Empresa cadastrada com município configurado
    - Credenciais NFS-e configuradas (menu Configurações > NFS-e)

    **Período padrão:** Últimos 30 dias (se não especificado)
    **Período máximo:** 365 dias por consulta

    **Sistemas suportados:**
    - Sistema Nacional (ABRASF) - ~3.000 municípios
    - Belo Horizonte/MG - BHISSDigital
    - São Paulo/SP - NF Paulistana
    """,
)
async def buscar_nfse_empresa(
    empresa_id: str,
    request: BuscarNFSeRequest = BuscarNFSeRequest(),
    current_user: dict = Depends(get_current_user),
    db=Depends(get_admin_db),
):
    """
    Busca NFS-e de uma empresa via API municipal.
    """
    try:
        # 1. Validar acesso à empresa
        if not await verificar_acesso_empresa(current_user["id"], empresa_id, db):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Você não tem permissão para acessar esta empresa",
            )

        # 2. Definir período (padrão: últimos 30 dias)
        data_fim = request.data_fim or date.today()
        data_inicio = request.data_inicio or (data_fim - timedelta(days=30))

        # 3. Validações de período
        if data_inicio > data_fim:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Data inicial não pode ser maior que data final",
            )

        if (data_fim - data_inicio).days > 365:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Período máximo de consulta é 365 dias",
            )

        # 4. Buscar notas via serviço
        resultado = await nfse_service.buscar_notas_empresa(
            empresa_id=empresa_id,
            data_inicio=data_inicio,
            data_fim=data_fim,
            usuario_id=current_user["id"],
        )

        return resultado

    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
    except NFSeAuthException as e:
        logger.error(f"[NFS-e] Erro de autenticação: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "error": "nfse_auth_error",
                "mensagem": e.mensagem,
                "detalhes": e.detalhes,
            },
        )
    except NFSeConfigException as e:
        logger.error(f"[NFS-e] Erro de configuração: {e}")
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "error": "nfse_config_error",
                "mensagem": e.mensagem,
            },
        )
    except NFSeSearchException as e:
        logger.error(f"[NFS-e] Erro na busca: {e}")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={
                "error": "nfse_search_error",
                "mensagem": e.mensagem,
                "detalhes": e.detalhes,
            },
        )
    except NFSeException as e:
        logger.error(f"[NFS-e] Erro genérico: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error": "nfse_error",
                "codigo": e.codigo,
                "mensagem": e.mensagem,
            },
        )
    except Exception as e:
        logger.error(f"[NFS-e] Erro inesperado: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erro interno ao buscar NFS-e: {str(e)}",
        )


# ============================================
# ENDPOINTS DE INFORMAÇÃO
# ============================================

@router.get(
    "/municipios/suportados",
    summary="Listar municípios com API NFS-e implementada",
    description="""
    Retorna a lista de municípios que possuem integração com API de NFS-e.

    Municípios não listados individualmente são atendidos pelo
    Sistema Nacional de NFS-e (ABRASF), que cobre ~3.000 municípios.
    """,
)
async def listar_municipios_suportados():
    """
    Lista municípios com API de NFS-e implementada.
    """
    return {
        "success": True,
        "municipios": nfse_service.listar_municipios_suportados(),
        "total": len(nfse_service.listar_municipios_suportados()),
    }


# ============================================
# ENDPOINTS DE CREDENCIAIS
# ============================================

@router.post(
    "/empresas/{empresa_id}/credenciais",
    summary="Configurar credenciais NFS-e de uma empresa",
    description="""
    Salva ou atualiza as credenciais de acesso à API municipal de NFS-e.

    **Como obter credenciais:**
    1. Acesse o portal NFS-e do seu município
    2. Cadastre-se como prestador de serviços
    3. Gere login/senha para acesso à API
    4. Insira as credenciais aqui

    As credenciais são armazenadas de forma segura e são específicas
    por empresa + município.
    """,
    status_code=status.HTTP_201_CREATED,
)
async def salvar_credenciais_nfse(
    empresa_id: str,
    request: SalvarCredenciaisRequest,
    current_user: dict = Depends(get_current_user),
    db=Depends(get_admin_db),
):
    """
    Salva credenciais NFS-e para uma empresa.
    """
    try:
        # Validar acesso
        if not await verificar_acesso_empresa(current_user["id"], empresa_id, db):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Você não tem permissão para acessar esta empresa",
            )

        resultado = await nfse_service.salvar_credenciais(
            empresa_id=empresa_id,
            municipio_codigo=request.municipio_codigo,
            usuario=request.usuario,
            senha=request.senha,
            cnpj=request.cnpj,
            token=request.token,
        )

        return {
            "success": True,
            "message": "Credenciais NFS-e salvas com sucesso",
            "credencial": {
                "id": resultado.get("id"),
                "municipio_codigo": resultado.get("municipio_codigo"),
                "usuario": resultado.get("usuario"),
                "ativo": resultado.get("ativo"),
            },
        }

    except HTTPException:
        raise
    except NFSeConfigException as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=e.mensagem,
        )
    except Exception as e:
        logger.error(f"[NFS-e] Erro ao salvar credenciais: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erro ao salvar credenciais: {str(e)}",
        )


@router.get(
    "/empresas/{empresa_id}/credenciais",
    summary="Listar credenciais NFS-e configuradas",
    description="""
    Lista as credenciais NFS-e configuradas para uma empresa.

    **Segurança:** A senha NÃO é retornada neste endpoint.
    Apenas informações de identificação (usuário, município, status).
    """,
)
async def listar_credenciais_nfse(
    empresa_id: str,
    current_user: dict = Depends(get_current_user),
    db=Depends(get_admin_db),
):
    """
    Lista credenciais NFS-e de uma empresa (sem senha).
    """
    try:
        # Validar acesso
        if not await verificar_acesso_empresa(current_user["id"], empresa_id, db):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Você não tem permissão para acessar esta empresa",
            )

        credenciais = await nfse_service.listar_credenciais_empresa(empresa_id)

        return {
            "success": True,
            "empresa_id": empresa_id,
            "credenciais": credenciais,
            "total": len(credenciais),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[NFS-e] Erro ao listar credenciais: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erro ao listar credenciais: {str(e)}",
        )


# ============================================
# ENDPOINT DE TESTE DE CONEXÃO
# ============================================

@router.post(
    "/empresas/{empresa_id}/testar-conexao",
    summary="Testar conexão com API municipal de NFS-e",
    description="""
    Testa se as credenciais configuradas permitem autenticação
    na API municipal de NFS-e.

    **Não busca notas** - apenas verifica se a autenticação funciona.
    Útil para validar credenciais antes de fazer consultas.
    """,
)
async def testar_conexao_nfse(
    empresa_id: str,
    current_user: dict = Depends(get_current_user),
    db=Depends(get_admin_db),
):
    """
    Testa autenticação na API municipal de NFS-e.
    """
    try:
        # Validar acesso
        if not await verificar_acesso_empresa(current_user["id"], empresa_id, db):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Você não tem permissão para acessar esta empresa",
            )

        # Buscar dados da empresa
        empresa_result = db.table("empresas")\
            .select("cnpj, municipio_codigo")\
            .eq("id", empresa_id)\
            .single()\
            .execute()

        if not empresa_result.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Empresa não encontrada",
            )

        municipio_codigo = empresa_result.data.get("municipio_codigo", "")

        # Buscar credenciais
        cred_result = db.table("credenciais_nfse")\
            .select("usuario, senha, token, cnpj")\
            .eq("empresa_id", empresa_id)\
            .eq("ativo", True)\
            .execute()

        if not cred_result.data:
            return {
                "success": False,
                "status": "sem_credenciais",
                "mensagem": "Nenhuma credencial NFS-e configurada para esta empresa",
            }

        # Selecionar adapter e testar autenticação
        cred = cred_result.data[0]
        credentials = {
            "usuario": cred.get("usuario"),
            "senha": cred.get("senha"),
            "token": cred.get("token"),
            "cnpj": cred.get("cnpj"),
        }

        adapter = nfse_service.obter_adapter(municipio_codigo, credentials)

        try:
            await adapter.autenticar()
            return {
                "success": True,
                "status": "conectado",
                "sistema": adapter.SISTEMA_NOME,
                "mensagem": f"Autenticação bem-sucedida no {adapter.SISTEMA_NOME}",
            }
        except NFSeAuthException as e:
            return {
                "success": False,
                "status": "falha_autenticacao",
                "sistema": adapter.SISTEMA_NOME,
                "mensagem": e.mensagem,
                "detalhes": e.detalhes,
            }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[NFS-e] Erro ao testar conexão: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erro ao testar conexão: {str(e)}",
        )
