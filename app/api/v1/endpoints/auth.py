"""
Endpoints de autenticação
"""
import time
from collections import defaultdict
from threading import Lock
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, status, Request
from supabase import Client
from pydantic import ValidationError

from app.dependencies import get_admin_db, get_current_user
from app.schemas.auth import LoginRequest, RefreshTokenRequest, TokenResponse
from app.services.auth_service import (
    authenticate_user,
    create_tokens_for_user,
    refresh_tokens_for_user,
)
from app.services.user_service import get_user_com_plano
from app.models.usuario import UsuarioComPlano
from app.core.token_blacklist import token_blacklist
from app.core.security import decode_access_token

router = APIRouter()


# Rate limiter para proteção contra brute force
class LoginRateLimiter:
    """Limita tentativas de login por IP"""
    def __init__(self, max_attempts: int = 5, window_seconds: int = 60):
        self._attempts: dict[str, list[float]] = defaultdict(list)
        self._lock = Lock()
        self.max_attempts = max_attempts
        self.window_seconds = window_seconds

    def is_blocked(self, ip: str) -> bool:
        """Verifica se IP está bloqueado"""
        with self._lock:
            now = time.time()
            # Remove tentativas fora da janela
            self._attempts[ip] = [
                t for t in self._attempts[ip]
                if now - t < self.window_seconds
            ]
            return len(self._attempts[ip]) >= self.max_attempts

    def record_attempt(self, ip: str):
        """Registra tentativa de login falhada"""
        with self._lock:
            self._attempts[ip].append(time.time())


login_rate_limiter = LoginRateLimiter(max_attempts=5, window_seconds=60)


async def _read_payload(request: Request) -> Dict[str, Any]:
    content_type = request.headers.get("content-type", "").lower()

    if "application/x-www-form-urlencoded" in content_type or "multipart/form-data" in content_type:
        return dict(await request.form())

    try:
        body = await request.json()
        if isinstance(body, dict):
            return body
    except Exception:
        pass

    return {}


def _normalize_login_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "email": payload.get("email") or payload.get("username"),
        "password": payload.get("password") or payload.get("senha"),
    }


async def _parse_login_request(request: Request) -> LoginRequest:
    payload = _normalize_login_payload(await _read_payload(request))

    try:
        return LoginRequest.model_validate(payload)
    except ValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=exc.errors(),
        )


async def _parse_refresh_request(request: Request) -> RefreshTokenRequest:
    payload = await _read_payload(request)
    refresh_token = payload.get("refresh_token") or payload.get("token")

    try:
        return RefreshTokenRequest.model_validate({"refresh_token": refresh_token})
    except ValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=exc.errors(),
        )


@router.post("/login", response_model=TokenResponse)
async def login(
    request: Request,
    db: Client = Depends(get_admin_db)  # Usa admin para bypass RLS no login
):
    """
    Login de usuário com email e senha

    Returns:
        Tokens de acesso (access_token e refresh_token)
    """
    client_ip = request.client.host if request.client else "unknown"

    # Verificar rate limit
    if login_rate_limiter.is_blocked(client_ip):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Muitas tentativas de login. Tente novamente em 1 minuto.",
            headers={"Retry-After": "60"}
        )

    login_request = await _parse_login_request(request)
    user = await authenticate_user(db, login_request.email, login_request.password)

    if not user:
        # Registrar tentativa falhada apenas em caso de falha
        login_rate_limiter.record_attempt(client_ip)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Email ou senha incorretos",
            headers={"WWW-Authenticate": "Bearer"},
        )

    tokens = create_tokens_for_user(user)
    return tokens


@router.post("/refresh", response_model=TokenResponse)
async def refresh(
    request: Request,
    db: Client = Depends(get_admin_db),
):
    """
    Renova os tokens usando um refresh token válido.

    O refresh token deve ser enviado no corpo da requisição.
    """
    refresh_request = await _parse_refresh_request(request)
    tokens = await refresh_tokens_for_user(db, refresh_request.refresh_token)

    if not tokens:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token inválido ou expirado",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return tokens


@router.post("/logout")
async def logout(
    request: Request,
    usuario: dict = Depends(get_current_user)
):
    """
    Logout de usuário - revoga o token atual adicionando à blacklist

    **Requer autenticação**

    Returns:
        Mensagem de sucesso
    """
    try:
        # Extrair token do header Authorization
        authorization = request.headers.get("Authorization", "")
        if not authorization.startswith("Bearer "):
            return {"message": "Logout realizado com sucesso"}

        token = authorization.replace("Bearer ", "")

        # Decodificar para extrair jti e exp
        try:
            payload = decode_access_token(token)
            jti = payload.get("jti")
            exp = payload.get("exp")

            if jti and exp:
                token_blacklist.add(jti, exp)
        except Exception:
            # Se falhar ao decodificar, apenas retorna sucesso
            pass

        return {"message": "Logout realizado com sucesso"}

    except Exception as e:
        # Mesmo com erro, retorna sucesso para não quebrar frontend
        return {"message": "Logout realizado com sucesso"}


@router.get("/me", response_model=UsuarioComPlano)
async def get_current_user_info(
    usuario: dict = Depends(get_current_user),
    db: Client = Depends(get_admin_db)  # Usa admin para bypass RLS
):
    """
    Retorna informações do usuário autenticado com dados do plano

    **Requer autenticação**

    Returns:
        Dados do usuário logado incluindo informações do plano ativo
    """
    user_com_plano = await get_user_com_plano(db, usuario["id"])

    if not user_com_plano:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Usuário não encontrado"
        )

    return user_com_plano
