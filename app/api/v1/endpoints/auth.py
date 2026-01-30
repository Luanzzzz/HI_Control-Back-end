"""
Endpoints de autenticação
"""
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from supabase import Client

from app.dependencies import get_db, get_admin_db, get_current_user
from app.schemas.auth import TokenResponse
from app.services.auth_service import authenticate_user, create_tokens_for_user
from app.services.user_service import get_user_com_plano
from app.models.usuario import UsuarioComPlano

router = APIRouter()


@router.post("/login", response_model=TokenResponse)
async def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Client = Depends(get_admin_db)  # Usa admin para bypass RLS no login
):
    """
    Login de usuário com email e senha

    **Credenciais de teste:**
    - teste@hicontrol.com.br / HiControl@2024 (Plano Profissional)

    Returns:
        Tokens de acesso (access_token e refresh_token)
    """
    user = await authenticate_user(db, form_data.username, form_data.password)

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Email ou senha incorretos",
            headers={"WWW-Authenticate": "Bearer"},
        )

    tokens = create_tokens_for_user(user)
    return tokens


@router.post("/logout")
async def logout(usuario: dict = Depends(get_current_user)):
    """
    Logout de usuário

    **Nota:** Implementação futura incluirá blacklist de tokens com Redis

    Returns:
        Mensagem de sucesso
    """
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
