"""
Dependências reutilizáveis para endpoints FastAPI
"""
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from supabase import Client
from app.db.supabase_client import supabase_client, supabase_admin
from app.core.config import settings
from jose import JWTError, jwt
from typing import Optional
import logging

logger = logging.getLogger(__name__)

security = HTTPBearer()


def get_db() -> Client:
    """
    Dependency que retorna cliente Supabase normal.
    Usa Row Level Security (RLS).
    """
    return supabase_client


def get_admin_db() -> Client:
    """
    Dependency que retorna cliente Supabase admin.
    Bypassa Row Level Security - usar com cuidado!
    """
    return supabase_admin


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Client = Depends(get_admin_db)  # Usa admin para bypass RLS com JWT customizado
):
    """
    Valida JWT token e retorna usuário atual.

    Args:
        credentials: Credenciais do header Authorization
        db: Cliente Supabase

    Returns:
        Dados do usuário autenticado

    Raises:
        HTTPException: Se token inválido ou usuário não encontrado
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Não foi possível validar as credenciais",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        # Decodificar JWT
        token = credentials.credentials
        payload = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[settings.ALGORITHM]
        )

        user_id: str = payload.get("sub")
        if user_id is None:
            raise credentials_exception

        # Buscar usuário no Supabase
        response = db.table("usuarios")\
            .select("*")\
            .eq("id", user_id)\
            .single()\
            .execute()

        if not response.data:
            raise credentials_exception

        usuario = response.data

        # Verificar se usuário está ativo
        if not usuario.get("ativo"):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Usuário inativo"
            )

        return usuario

    except JWTError:
        raise credentials_exception
    except Exception as e:
        logger.error(f"Erro ao validar token: {e}")
        raise credentials_exception


async def verificar_acesso_modulo(
    modulo: str,
    usuario: dict = Depends(get_current_user),
    db: Client = Depends(get_db)
):
    """
    Verifica se usuário tem acesso ao módulo solicitado.

    Args:
        modulo: Nome do módulo (ex: 'buscador_notas')
        usuario: Dados do usuário autenticado
        db: Cliente Supabase

    Raises:
        HTTPException 403: Se usuário não tem acesso ao módulo
    """
    # 🚧 BYPASS para desenvolvimento: permite acesso a todos os módulos
    # Em produção, DEVE ter DISABLE_MODULE_CHECK=false ou não definido
    import os
    # Bypass em ambiente de desenvolvimento OU se DISABLE_MODULE_CHECK=true
    if (os.getenv("ENVIRONMENT") == "development" or
        os.getenv("DISABLE_MODULE_CHECK", "false").lower() == "true"):
        logger.warning(
            f"🔓 [DEV MODE] MÓDULO '{modulo}' - Verificação DESABILITADA. "
            f"Usuário {usuario.get('email')} tem acesso IRRESTRITO. "
            f"Ambiente: {os.getenv('ENVIRONMENT', 'unknown')} | "
            f"DISABLE_MODULE_CHECK: {os.getenv('DISABLE_MODULE_CHECK', 'false')} | "
            f"⚠️ ATENÇÃO: Isso NÃO deve estar ativo em produção!"
        )
        return True

    try:
        # Buscar assinatura ativa do usuário
        response = db.table("assinaturas")\
            .select("*, planos!inner(modulos_disponiveis)")\
            .eq("usuario_id", usuario["id"])\
            .eq("status", "ativa")\
            .gte("data_fim", "now()")\
            .execute()

        if not response.data or len(response.data) == 0:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Nenhuma assinatura ativa encontrada"
            )

        assinatura = response.data[0]
        modulos_disponiveis = assinatura["planos"]["modulos_disponiveis"]

        if modulo not in modulos_disponiveis:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Seu plano não inclui o módulo '{modulo}'. Faça upgrade para acessar."
            )

        return True

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erro ao verificar acesso ao módulo: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro ao verificar permissões"
        )


def require_modules(*modulos: str):
    """
    Decorator para proteger endpoints que requerem módulos específicos.

    Uso:
        @router.get("/notas/buscar")
        @require_modules("buscador_notas")
        async def buscar_notas(...):
            ...
    """
    async def dependency(usuario: dict = Depends(get_current_user)):
        for modulo in modulos:
            await verificar_acesso_modulo(modulo, usuario, get_db())
        return usuario

    return Depends(dependency)
