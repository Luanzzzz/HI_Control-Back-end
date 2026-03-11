"""
Modelos Pydantic para Empresa
"""
from pydantic import BaseModel, Field, field_validator
from typing import Optional, Literal
from datetime import date, datetime
import re


def validar_cnpj_algoritmo(cnpj_digits: str) -> bool:
    """
    Valida CNPJ brasileiro pelo algoritmo dos dígitos verificadores.
    Recebe apenas dígitos (14 caracteres).
    """
    if len(cnpj_digits) != 14:
        return False

    # Rejeitar CNPJs com todos os dígitos iguais
    if cnpj_digits == cnpj_digits[0] * 14:
        return False

    # Primeiro dígito verificador
    pesos1 = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    soma1 = sum(int(cnpj_digits[i]) * pesos1[i] for i in range(12))
    d1 = 11 - (soma1 % 11)
    d1 = 0 if d1 >= 10 else d1

    if int(cnpj_digits[12]) != d1:
        return False

    # Segundo dígito verificador
    pesos2 = [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    soma2 = sum(int(cnpj_digits[i]) * pesos2[i] for i in range(13))
    d2 = 11 - (soma2 % 11)
    d2 = 0 if d2 >= 10 else d2

    if int(cnpj_digits[13]) != d2:
        return False

    return True


class EmpresaBase(BaseModel):
    """Modelo base de empresa"""
    usuario_id: Optional[str] = None
    razao_social: str = Field(..., max_length=255)
    nome_fantasia: Optional[str] = Field(None, max_length=255)
    cnpj: str = Field(..., min_length=14, max_length=18)
    inscricao_estadual: Optional[str] = Field(None, max_length=50)
    inscricao_municipal: Optional[str] = Field(None, max_length=50)

    # Endereço
    cep: Optional[str] = Field(None, max_length=10)
    logradouro: Optional[str] = Field(None, max_length=255)
    numero: Optional[str] = Field(None, max_length=20)
    complemento: Optional[str] = Field(None, max_length=100)
    bairro: Optional[str] = Field(None, max_length=100)
    cidade: Optional[str] = Field(None, max_length=100)
    estado: Optional[str] = Field(None, max_length=2)
    municipio_codigo: Optional[str] = Field(None, min_length=7, max_length=7)
    municipio_nome: Optional[str] = Field(None, max_length=100)

    # Contato
    email: Optional[str] = None
    telefone: Optional[str] = Field(None, max_length=20)

    # Regime tributário
    regime_tributario: Optional[Literal["simples_nacional", "lucro_presumido", "lucro_real"]] = None

    # Certificado Digital
    certificado_validade: Optional[date] = None

    @field_validator('cnpj')
    @classmethod
    def validar_cnpj(cls, v: str) -> str:
        """Valida formato, dígitos verificadores e formata CNPJ"""
        # Remove caracteres não numéricos
        cnpj = re.sub(r'\D', '', v)

        if len(cnpj) != 14:
            raise ValueError("CNPJ deve conter 14 dígitos")

        if not validar_cnpj_algoritmo(cnpj):
            raise ValueError("CNPJ inválido - dígitos verificadores incorretos")

        # Formata: 00.000.000/0000-00
        return f"{cnpj[:2]}.{cnpj[2:5]}.{cnpj[5:8]}/{cnpj[8:12]}-{cnpj[12:]}"

    @field_validator('cep')
    @classmethod
    def validar_cep(cls, v: Optional[str]) -> Optional[str]:
        """Valida e formata CEP"""
        if v is None:
            return v

        # Remove caracteres não numéricos
        cep = re.sub(r'\D', '', v)

        if len(cep) != 8:
            raise ValueError("CEP deve conter 8 dígitos")

        # Formata: 00000-000
        return f"{cep[:5]}-{cep[5:]}"

    @field_validator('estado')
    @classmethod
    def validar_estado(cls, v: Optional[str]) -> Optional[str]:
        """Valida sigla de estado (UF)"""
        if v is None:
            return v

        v = v.upper()
        estados_validos = [
            "AC", "AL", "AP", "AM", "BA", "CE", "DF", "ES", "GO", "MA",
            "MT", "MS", "MG", "PA", "PB", "PR", "PE", "PI", "RJ", "RN",
            "RS", "RO", "RR", "SC", "SP", "SE", "TO"
        ]

        if v not in estados_validos:
            raise ValueError(f"Estado inválido. Use uma das siglas válidas: {', '.join(estados_validos)}")

        return v


class EmpresaCreate(EmpresaBase):
    """Schema para criação de empresa"""
    pass


class EmpresaResponse(EmpresaBase):
    """Schema de resposta"""
    id: str
    ativa: bool
    created_at: datetime
    updated_at: datetime
    deleted_at: Optional[datetime] = None

    class Config:
        from_attributes = True
