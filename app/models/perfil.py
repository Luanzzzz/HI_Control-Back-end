"""
Modelos Pydantic para Perfil de Contabilidade
"""
from pydantic import BaseModel, Field, field_validator
from typing import Optional
from datetime import datetime
import re

class PerfilBase(BaseModel):
    """Modelo base de perfil da contabilidade"""
    nome_empresa: Optional[str] = Field(None, max_length=255)
    cnpj: Optional[str] = Field(None, min_length=14, max_length=18)
    logo_url: Optional[str] = None

    @field_validator('cnpj')
    @classmethod
    def validar_cnpj(cls, v: Optional[str]) -> Optional[str]:
        """Valida e formata CNPJ se fornecido"""
        if v is None:
            return v
            
        # Remove caracteres não numéricos
        cnpj = re.sub(r'\D', '', v)

        if len(cnpj) != 14:
            raise ValueError("CNPJ deve conter 14 dígitos")

        # Formata: 00.000.000/0000-00
        return f"{cnpj[:2]}.{cnpj[2:5]}.{cnpj[5:8]}/{cnpj[8:12]}-{cnpj[12:]}"

class PerfilCreate(PerfilBase):
    """Schema para criação/atualização de perfil"""
    pass

class PerfilResponse(PerfilBase):
    """Schema de resposta"""
    id: str
    usuario_id: str
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True
