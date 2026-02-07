"""
Modelos Pydantic para Nota Fiscal
"""
from pydantic import BaseModel, Field, field_validator
from typing import Optional, Literal, List
from datetime import datetime, date
from decimal import Decimal
import re


class NotaFiscalBase(BaseModel):
    """
    Modelo base para Nota Fiscal.
    Compartilhado entre requests e responses.
    """
    numero_nf: str = Field(..., min_length=1, max_length=20, description="Número da nota fiscal")
    serie: str = Field(..., min_length=1, max_length=10, description="Série da nota")
    tipo_nf: Literal["NFe", "NFSe", "NFCe", "CTe"] = Field(..., description="Tipo de nota fiscal")
    modelo: Optional[str] = Field(None, max_length=5, description="Modelo fiscal (55, 65, 57, etc)")

    chave_acesso: Optional[str] = Field(None, min_length=44, max_length=44, description="Chave de acesso de 44 dígitos")

    data_emissao: datetime = Field(..., description="Data e hora de emissão")
    data_autorizacao: Optional[datetime] = Field(None, description="Data e hora de autorização")

    valor_total: Decimal = Field(..., ge=0, decimal_places=2, description="Valor total da nota")
    valor_produtos: Optional[Decimal] = Field(None, ge=0, decimal_places=2)
    valor_servicos: Optional[Decimal] = Field(None, ge=0, decimal_places=2)

    cnpj_emitente: str = Field(..., min_length=14, max_length=18, description="CNPJ do emitente")
    nome_emitente: Optional[str] = Field(None, max_length=255)
    cnpj_destinatario: Optional[str] = Field(None, min_length=14, max_length=18)
    nome_destinatario: Optional[str] = Field(None, max_length=255)

    situacao: str = Field(default="processando", description="Situação atual da nota")
    protocolo: Optional[str] = Field(None, max_length=50)

    xml_url: Optional[str] = Field(None, description="URL do XML no Supabase Storage")
    pdf_url: Optional[str] = Field(None, description="URL do DANFE em PDF")
    xml_resumo: Optional[str] = Field(None, description="XML resumo (resNFe) da DistribuicaoDFe")

    observacoes: Optional[str] = None

    @field_validator('chave_acesso')
    @classmethod
    def validar_chave_acesso(cls, v: Optional[str]) -> Optional[str]:
        """Valida formato da chave de acesso (44 dígitos numéricos)"""
        if v is None:
            return v

        # Remove espaços
        v = v.replace(" ", "")

        if not v.isdigit() or len(v) != 44:
            raise ValueError("Chave de acesso deve conter exatamente 44 dígitos numéricos")

        return v

    @field_validator('cnpj_emitente', 'cnpj_destinatario')
    @classmethod
    def validar_cnpj(cls, v: Optional[str]) -> Optional[str]:
        """Valida e formata CNPJ"""
        if v is None:
            return v

        # Remove caracteres não numéricos
        cnpj = re.sub(r'\D', '', v)

        if len(cnpj) != 14:
            raise ValueError("CNPJ deve conter 14 dígitos")

        # Formata: 00.000.000/0000-00
        return f"{cnpj[:2]}.{cnpj[2:5]}.{cnpj[5:8]}/{cnpj[8:12]}-{cnpj[12:]}"

    class Config:
        json_schema_extra = {
            "example": {
                "numero_nf": "000000123",
                "serie": "1",
                "tipo_nf": "NFe",
                "modelo": "55",
                "chave_acesso": "35240112345678000190550010000001231234567890",
                "data_emissao": "2024-01-15T10:30:00",
                "valor_total": 1500.00,
                "cnpj_emitente": "12.345.678/0001-90",
                "nome_emitente": "Empresa Exemplo LTDA",
                "situacao": "autorizada"
            }
        }


class NotaFiscalCreate(NotaFiscalBase):
    """Schema para criacao de nota fiscal (inclui campos de importacao XML)"""
    empresa_id: str = Field(..., description="UUID da empresa")

    # Campos adicionais para importacao de XML
    tipo_operacao: Optional[str] = Field(None, description="entrada ou saida")
    ie_emitente: Optional[str] = Field(None, description="Inscricao Estadual do emitente")
    cpf_destinatario: Optional[str] = Field(None, description="CPF do destinatario (PF)")
    valor_icms: Optional[Decimal] = Field(None, ge=0, decimal_places=2)
    valor_ipi: Optional[Decimal] = Field(None, ge=0, decimal_places=2)
    valor_pis: Optional[Decimal] = Field(None, ge=0, decimal_places=2)
    valor_cofins: Optional[Decimal] = Field(None, ge=0, decimal_places=2)
    valor_frete: Optional[Decimal] = Field(None, ge=0, decimal_places=2)
    valor_desconto: Optional[Decimal] = Field(None, ge=0, decimal_places=2)
    fonte: Optional[str] = Field(None, description="Origem da nota: xml_importado, sefaz, manual")
    xml_completo: Optional[str] = Field(None, description="XML completo da nota")

    @field_validator('cnpj_emitente', 'cnpj_destinatario', mode='before')
    @classmethod
    def normalizar_cnpj_create(cls, v: Optional[str]) -> Optional[str]:
        """Aceita CNPJ em qualquer formato e normaliza"""
        if v is None:
            return v
        # Remove caracteres nao numericos
        cnpj = re.sub(r'\D', '', str(v))
        if len(cnpj) == 14:
            # Formata: 00.000.000/0000-00
            return f"{cnpj[:2]}.{cnpj[2:5]}.{cnpj[5:8]}/{cnpj[8:12]}-{cnpj[12:]}"
        return v


class NotaFiscalResponse(NotaFiscalBase):
    """Schema de resposta com campos adicionais do banco"""
    id: Optional[str] = None
    empresa_id: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    deleted_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class NotaFiscalDetalhada(NotaFiscalResponse):
    """Schema com informações completas incluindo impostos"""
    valor_icms: Optional[Decimal] = None
    valor_ipi: Optional[Decimal] = None
    valor_pis: Optional[Decimal] = None
    valor_cofins: Optional[Decimal] = None
    motivo_cancelamento: Optional[str] = None
    tags: Optional[List[str]] = Field(default_factory=list)


class NotaFiscalSearchParams(BaseModel):
    """Parâmetros de busca de Notas Fiscais"""

    search_term: Optional[str] = Field(None, description="Termo de busca geral")
    tipo_nf: Optional[Literal["NFe", "NFSe", "NFCe", "CTe", "TODAS"]] = Field("TODAS", description="Filtro por tipo")
    situacao: Optional[str] = Field(None, description="Filtro por situação")
    data_inicio: Optional[datetime] = Field(None, description="Data inicial")
    data_fim: Optional[datetime] = Field(None, description="Data final")
    cnpj_emitente: Optional[str] = Field(None, description="Filtro por CNPJ emitente")
    skip: int = Field(0, ge=0, description="Paginação - offset")
    limit: int = Field(100, ge=1, le=1000, description="Paginação - limite")


class BuscaNotaFilter(BaseModel):
    """
    Filtros para busca de notas fiscais (versão expandida)
    """
    tipo_nf: Optional[Literal["NFe", "NFSe", "NFCe", "CTe"]] = None
    cnpj_emitente: Optional[str] = Field(None, min_length=14, max_length=18)
    data_inicio: date
    data_fim: date
    numero_nf: Optional[str] = Field(None, max_length=20)
    serie: Optional[str] = Field(None, max_length=10)
    situacao: Optional[Literal["autorizada", "cancelada", "denegada", "processando"]] = None
    chave_acesso: Optional[str] = Field(None, min_length=44, max_length=44)

    @field_validator('data_inicio', 'data_fim')
    @classmethod
    def validar_datas(cls, v):
        """Valida que as datas não são futuras"""
        if v > date.today():
            raise ValueError("Data não pode ser futura")
        return v

    class Config:
        json_schema_extra = {
            "example": {
                "tipo_nf": "NFe",
                "data_inicio": "2024-01-01",
                "data_fim": "2024-01-31",
                "situacao": "autorizada"
            }
        }
