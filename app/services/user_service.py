"""
Serviço de gerenciamento de usuários
"""
from typing import Optional
from supabase import Client
from app.models.usuario import UsuarioResponse, UsuarioComPlano


async def get_user_by_email(db: Client, email: str) -> Optional[dict]:
    """
    Busca usuário por email

    Args:
        db: Cliente Supabase
        email: Email do usuário

    Returns:
        Dados do usuário encontrado ou None
    """
    try:
        response = db.table("usuarios")\
            .select("*")\
            .eq("email", email)\
            .single()\
            .execute()

        return response.data if response.data else None
    except Exception:
        return None


async def get_user_by_id(db: Client, user_id: str) -> Optional[dict]:
    """
    Busca usuário por ID

    Args:
        db: Cliente Supabase
        user_id: ID do usuário

    Returns:
        Dados do usuário encontrado ou None
    """
    try:
        response = db.table("usuarios")\
            .select("*")\
            .eq("id", user_id)\
            .single()\
            .execute()

        return response.data if response.data else None
    except Exception:
        return None


async def get_user_com_plano(db: Client, user_id: str) -> Optional[UsuarioComPlano]:
    """
    Busca usuário com informações do plano ativo

    Args:
        db: Cliente Supabase
        user_id: ID do usuário

    Returns:
        UsuarioComPlano ou None
    """
    try:
        # Buscar usuário
        user = await get_user_by_id(db, user_id)
        if not user:
            return None

        # Buscar assinatura ativa com plano
        response = db.table("assinaturas")\
            .select("*, planos!inner(*)")\
            .eq("usuario_id", user_id)\
            .eq("status", "ativa")\
            .gte("data_fim", "now()")\
            .limit(1)\
            .execute()

        plano_nome = None
        plano_ativo = False
        modulos_disponiveis = []

        if response.data and len(response.data) > 0:
            assinatura = response.data[0]
            plano = assinatura.get("planos")
            if plano:
                plano_nome = plano.get("nome")
                plano_ativo = True
                modulos_disponiveis = plano.get("modulos_disponiveis", [])

        return UsuarioComPlano(
            id=user["id"],
            email=user["email"],
            nome_completo=user["nome_completo"],
            cpf=user.get("cpf"),
            telefone=user.get("telefone"),
            avatar_url=user.get("avatar_url"),
            ativo=user["ativo"],
            email_verificado=user["email_verificado"],
            created_at=user["created_at"],
            plano_nome=plano_nome,
            plano_ativo=plano_ativo,
            modulos_disponiveis=modulos_disponiveis
        )

    except Exception:
        return None


def user_to_response(user: dict) -> UsuarioResponse:
    """
    Converte dict de usuário para UsuarioResponse schema

    Args:
        user: Dicionário com dados do usuário

    Returns:
        Schema de resposta de usuário
    """
    return UsuarioResponse(
        id=user["id"],
        email=user["email"],
        nome_completo=user["nome_completo"],
        cpf=user.get("cpf"),
        telefone=user.get("telefone"),
        avatar_url=user.get("avatar_url"),
        ativo=user["ativo"],
        email_verificado=user["email_verificado"],
        created_at=user["created_at"]
    )
