"""
Modelos Pydantic para consulta de NFes distribuídas (DistribuicaoDFe).

Estes modelos são específicos para BUSCA/CONSULTA de notas fiscais,
separados dos modelos de EMISSÃO (nfe_completa.py).

Referência: Manual DistribuicaoDFe v1.01
"""
from pydantic import BaseModel, Field, field_validator
from typing import Optional, List, Literal
from datetime import datetime
from decimal import Decimal


# ============================================
# REQUEST MODELS
# ============================================

class ConsultaDistribuicaoRequest(BaseModel):
    """
    Request para consulta de NFes distribuídas pela SEFAZ.
    
    Permite buscar notas sem certificado digital de emissão.
    """
    cnpj: str = Field(
        ..., 
        pattern=r'^\d{14}$', 
        description="CNPJ sem formatação (14 dígitos)"
    )
    nsu_inicial: Optional[int] = Field(
        None, 
        ge=0,
        description="NSU para retomar consulta (0 para iniciar do zero)"
    )
    max_notas: int = Field(
        default=50, 
        ge=1, 
        le=500, 
        description="Máximo de notas por consulta (limite SEFAZ: 500)"
    )

    @field_validator('cnpj')
    @classmethod
    def validar_cnpj(cls, v: str) -> str:
        """Valida formato CNPJ"""
        if not v.isdigit() or len(v) != 14:
            raise ValueError("CNPJ deve conter exatamente 14 dígitos numéricos")
        return v


# ============================================
# RESPONSE MODELS
# ============================================

class NFeBuscadaMetadata(BaseModel):
    """
    Metadados de uma NFe encontrada via DistribuicaoDFe (resNFe).

    Representa o resumo da nota retornado pela SEFAZ.
    """
    # Identificação
    chave_acesso: str = Field(..., min_length=44, max_length=44)
    nsu: int = Field(..., description="Número Sequencial Único SEFAZ")

    # Datas
    data_emissao: datetime = Field(..., description="Data/hora de emissão")

    # Tipo e valor
    tipo_operacao: Literal["0", "1"] = Field(
        ...,
        description="0=Entrada, 1=Saída"
    )
    valor_total: Decimal = Field(..., ge=0, decimal_places=2)

    # Emitente
    cnpj_emitente: str = Field(..., pattern=r'^\d{14}$')
    nome_emitente: str = Field(..., max_length=255)

    # Destinatário (opcional, pode não estar no resNFe)
    cnpj_destinatario: Optional[str] = Field(None, pattern=r'^\d{14}$')
    cpf_destinatario: Optional[str] = Field(None, pattern=r'^\d{11}$')
    nome_destinatario: Optional[str] = Field(None, max_length=255)

    # Status
    situacao: str = Field(
        ...,
        description="Situação da NFe: autorizada, cancelada, denegada"
    )
    situacao_codigo: str = Field(
        ...,
        description="Código situação SEFAZ (1=Autorizada, 2=Denegada, 3=Cancelada)"
    )

    # Protocolo (opcional)
    protocolo: Optional[str] = Field(None, max_length=50)

    # XML (opcional - armazena o resNFe completo para download)
    xml_resumo: Optional[str] = Field(
        None,
        description="XML resNFe completo retornado pela SEFAZ"
    )

    @field_validator('chave_acesso')
    @classmethod
    def validar_chave(cls, v: str) -> str:
        """Valida chave de acesso"""
        if not v.isdigit() or len(v) != 44:
            raise ValueError("Chave de acesso deve ter 44 dígitos")
        return v


class DistribuicaoResponseModel(BaseModel):
    """
    Response completo da consulta DistribuicaoDFe.
    
    Contém status da operação e lista de notas encontradas.
    """
    # Status da operação
    status_codigo: str = Field(
        ..., 
        description="Código retorno SEFAZ (138=Sucesso, 656=Consumo indevido)"
    )
    motivo: str = Field(..., description="Mensagem retorno SEFAZ")
    
    # Notas encontradas
    notas_encontradas: List[NFeBuscadaMetadata] = Field(
        default_factory=list,
        description="Lista de NFes encontradas"
    )
    
    # Controle de NSU
    ultimo_nsu: int = Field(
        ..., 
        ge=0,
        description="Último NSU disponível na SEFAZ"
    )
    max_nsu: int = Field(
        ...,
        ge=0, 
        description="NSU máximo atual na SEFAZ"
    )
    
    # Estatísticas
    total_notas: int = Field(..., ge=0, description="Quantidade de notas retornadas")
    
    @property
    def sucesso(self) -> bool:
        """Verifica se a consulta foi bem-sucedida"""
        return self.status_codigo == "138"
    
    @property
    def tem_mais_notas(self) -> bool:
        """Verifica se há mais notas para consultar"""
        return self.ultimo_nsu < self.max_nsu


# ============================================
# HELPER MODELS
# ============================================

class LimitesPlanoConsulta(BaseModel):
    """
    Limites de consulta baseados no plano do usuário.
    
    Usado internamente para controle de acesso.
    """
    historico_dias: Optional[int] = Field(
        None, 
        description="Limite de dias histórico (None=ilimitado)"
    )
    max_empresas: int = Field(..., ge=1, description="Máximo de CNPJs cadastrados")
    max_consultas_dia: int = Field(..., ge=1, description="Limite de consultas por dia")
    max_notas_por_consulta: int = Field(
        default=50,
        ge=1,
        le=500,
        description="Máximo de notas por requisição"
    )


class ConsultaDistribuicaoLog(BaseModel):
    """
    Log de consulta DistribuicaoDFe para auditoria.
    
    Armazenado na tabela sefaz_log.
    """
    empresa_id: str
    cnpj_consultado: str
    nsu_inicial: int
    nsu_final: int
    total_notas_encontradas: int
    status_codigo: str
    tempo_resposta_ms: Optional[int] = None
    sucesso: bool


# ============================================
# MAPEAMENTO DE SITUAÇÕES SEFAZ
# ============================================

SITUACAO_NFE_MAP = {
    "1": "autorizada",
    "2": "denegada", 
    "3": "cancelada",
}

def mapear_situacao_nfe(codigo: str) -> str:
    """
    Mapeia código de situação SEFAZ para string legível.
    
    Args:
        codigo: Código cSitNFe (1, 2, 3)
    
    Returns:
        String: "autorizada", "denegada", "cancelada"
    """
    return SITUACAO_NFE_MAP.get(codigo, "desconhecida")
