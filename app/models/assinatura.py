"""
Modelos Pydantic para Assinatura
"""
from pydantic import BaseModel, Field
from typing import Optional, Literal
from datetime import date, datetime
from decimal import Decimal


class AssinaturaBase(BaseModel):
    """Modelo base de assinatura"""
    usuario_id: str
    plano_id: str
    data_inicio: date = Field(default_factory=date.today)
    data_fim: date
    tipo_cobranca: Literal["mensal", "anual"] = "mensal"
    status: Literal["ativa", "cancelada", "suspensa", "trial"] = "ativa"
    valor_pago: Optional[Decimal] = Field(None, ge=0, decimal_places=2)
    metodo_pagamento: Optional[Literal["cartao", "boleto", "pix"]] = None
    gateway_pagamento_id: Optional[str] = None
    em_trial: bool = False
    trial_termina_em: Optional[date] = None


class AssinaturaCreate(AssinaturaBase):
    """Schema para criação de assinatura"""
    pass


class AssinaturaResponse(AssinaturaBase):
    """Schema de resposta"""
    id: str
    created_at: datetime
    updated_at: datetime
    cancelada_em: Optional[datetime] = None

    class Config:
        from_attributes = True
