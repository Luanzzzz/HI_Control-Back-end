"""
Modelos Pydantic para Usuário
"""
from pydantic import BaseModel, EmailStr, Field
from typing import Optional, List
from datetime import datetime


class UsuarioBase(BaseModel):
    """Modelo base de usuário"""
    email: EmailStr
    nome_completo: str = Field(..., min_length=3, max_length=255)
    cpf: Optional[str] = Field(None, pattern=r'^\d{3}\.\d{3}\.\d{3}-\d{2}$')
    telefone: Optional[str] = Field(None, max_length=20)
    avatar_url: Optional[str] = None


class UsuarioCreate(UsuarioBase):
    """Schema para criação de usuário"""
    senha: str = Field(..., min_length=8, description="Senha com mínimo 8 caracteres")


class UsuarioResponse(UsuarioBase):
    """Schema de resposta"""
    id: str
    ativo: bool
    email_verificado: bool
    created_at: datetime

    class Config:
        from_attributes = True


class UsuarioComPlano(UsuarioResponse):
    """Usuário com informações do plano atual"""
    plano_nome: Optional[str] = None
    plano_ativo: bool = False
    modulos_disponiveis: List[str] = Field(default_factory=list)
    is_admin: Optional[bool] = None
    role: Optional[str] = None
