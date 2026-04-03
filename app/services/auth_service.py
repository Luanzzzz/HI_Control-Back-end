"""
Serviço de autenticação
"""
from typing import Optional
from supabase import Client
import logging
import secrets
import asyncio

from fastapi import HTTPException

from app.core.security import (
    verify_password,
    create_access_token,
    create_refresh_token,
    decode_token,
)
from app.schemas.auth import TokenResponse
from app.services.user_service import get_user_by_id

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
        logger.info("[AUTH] Tentando autenticar usuário")

        # Buscar usuário por email
        response = db.table("usuarios")\
            .select("*")\
            .eq("email", email)\
            .limit(1)\
            .execute()

        usuarios = response.data or []
        if not usuarios:
            logger.warning("[AUTH] Falha na autenticacao")
            # Mitigação de timing attack: pausa aleatória (50-200ms) para simular verificação de senha
            await asyncio.sleep(secrets.randbelow(150) / 1000 + 0.05)
            return None

        user = usuarios[0]

        # Verificar senha
        hashed = user.get("hashed_password")

        password_valid = verify_password(password, hashed)

        if not password_valid:
            logger.warning("[AUTH] Falha na autenticacao")
            return None

        # Verificar se usuário está ativo
        if not user.get("ativo"):
            logger.warning("[AUTH] Falha na autenticacao")
            return None

        logger.info("[AUTH] Autenticacao bem sucedida")
        return user

    except Exception:
        logger.warning("[AUTH] Erro na autenticacao")
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
        "sub": user["id"]
    }

    access_token = create_access_token(token_data)
    refresh_token = create_refresh_token(token_data)

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer"
    )


async def refresh_tokens_for_user(db: Client, refresh_token: str) -> Optional[TokenResponse]:
    """
    Renova tokens a partir de um refresh token válido.

    Args:
        db: Cliente Supabase
        refresh_token: JWT de atualização

    Returns:
        Nova dupla de tokens ou None se inválido
    """
    try:
        payload = decode_token(refresh_token, expected_type="refresh")
        user_id = payload.get("sub")

        if not user_id:
            return None

        user = await get_user_by_id(db, user_id)
        if not user or not user.get("ativo"):
            return None

        return create_tokens_for_user(user)
    except HTTPException:
        return None
    except Exception:
        logger.warning("[AUTH] Erro ao renovar tokens")
        return None
