"""
Modelos Pydantic para Plano
"""
from pydantic import BaseModel, Field
from typing import Optional, List
from decimal import Decimal


class PlanoBase(BaseModel):
    """Modelo base de plano"""
    nome: str = Field(..., max_length=100)
    descricao: Optional[str] = None
    preco_mensal: Decimal = Field(..., ge=0, decimal_places=2)
    preco_anual: Optional[Decimal] = Field(None, ge=0, decimal_places=2)
    max_usuarios: int = Field(default=1, ge=1)
    max_empresas: int = Field(default=1, ge=1)
    max_notas_mes: int = Field(default=100, ge=0)
    modulos_disponiveis: List[str] = Field(default_factory=list)


class PlanoResponse(PlanoBase):
    """Schema de resposta"""
    id: str
    ativo: bool
    possui_api: bool
    possui_whatsapp: bool
    possui_relatorios_avancados: bool

    class Config:
        from_attributes = True
