"""
Serviço de autenticação
"""
from typing import Optional
from supabase import Client
import logging

from app.core.security import verify_password, create_access_token, create_refresh_token
from app.schemas.auth import TokenResponse

logger = logging.getLogger(__name__)


async def authenticate_user(db: Client, email: str, password: str) -> Optional[dict]:
    """
    Autentica usuário com email e senha

    Args:
        db: Cliente Supabase
        email: Email do usuário
        password: Senha em texto plano

    Returns:
        Dados do usuário autenticado ou None se credenciais inválidas
    """
    try:
        logger.info(f"[AUTH] Tentando autenticar: {email}")

        # Buscar usuário por email
        response = db.table("usuarios")\
            .select("*")\
            .eq("email", email)\
            .single()\
            .execute()

        if not response.data:
            logger.warning(f"[AUTH] Usuario nao encontrado: {email}")
            return None

        user = response.data
        logger.info(f"[AUTH] Usuario encontrado: {user.get('email')}, ativo: {user.get('ativo')}")

        # Verificar senha
        hashed = user.get("hashed_password")
        logger.info(f"[AUTH] Hash do banco: {hashed[:30] if hashed else 'VAZIO'}...")

        password_valid = verify_password(password, hashed)
        logger.info(f"[AUTH] Senha valida: {password_valid}")

        if not password_valid:
            logger.warning(f"[AUTH] Senha invalida para: {email}")
            return None

        # Verificar se usuário está ativo
        if not user.get("ativo"):
            logger.warning(f"[AUTH] Usuario inativo: {email}")
            return None

        logger.info(f"[AUTH] Autenticacao bem sucedida: {email}")
        return user

    except Exception as e:
        logger.error(f"[AUTH] Erro na autenticacao: {str(e)}")
        return None


def create_tokens_for_user(user: dict) -> TokenResponse:
    """
    Cria tokens JWT para o usuário

    Args:
        user: Dicionário com dados do usuário

    Returns:
        Tokens de acesso e refresh
    """
    token_data = {
        "sub": user["id"],
        "email": user["email"]
    }

    access_token = create_access_token(token_data)
    refresh_token = create_refresh_token(token_data)

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer"
    )
