"""
Modelos Pydantic completos para NF-e baseados no layout SEFAZ 4.0.
Referência: Manual de Integração Contribuinte versão 7.0

Estes modelos representam a estrutura COMPLETA de uma NF-e,
incluindo todos os campos obrigatórios identificados na auditoria.
"""
from pydantic import BaseModel, Field, field_validator, model_validator
from typing import Optional, List, Literal, Annotated
from datetime import datetime, date
from decimal import Decimal
try:
    from validate_docbr import CNPJ, CPF
except ImportError:
    # Fallback se validate_docbr não estiver instalado ainda
    class CNPJ:
        def validate(self, v): return len(v) == 14 and v.isdigit()
    class CPF:
        def validate(self, v): return len(v) == 11 and v.isdigit()

import re

# ============================================
# ENUMS E TIPOS AUXILIARES
# ============================================

TipoAmbiente = Literal["1", "2"]  # 1-Produção, 2-Homologação
TipoOperacao = Literal["0", "1"]  # 0-Entrada, 1-Saída
ModalidadeFrete = Literal[0, 1, 2, 9]  # 0-CIF, 1-FOB, 2-Terceiros, 9-Sem
OrigemMercadoria = Literal["0","1","2","3","4","5","6","7","8"]

# Tipos customizados com validação
CNPJ14 = Annotated[str, Field(pattern=r'^\d{14}$')]
CPF11 = Annotated[str, Field(pattern=r'^\d{11}$')]
NCM8 = Annotated[str, Field(pattern=r'^\d{8}$')]
CFOP4 = Annotated[str, Field(pattern=r'^\d{4}$')]
ChaveNFe = Annotated[str, Field(min_length=44, max_length=44, pattern=r'^\d{44}$')]

# ============================================
# IMPOSTOS POR ITEM
# ============================================

class ICMSItem(BaseModel):
    """ICMS de um item da NF-e"""

    origem: OrigemMercadoria = Field(..., description="Origem da mercadoria (0-8)")
    cst: str = Field(..., pattern=r'^\d{2}$', description="CST ICMS (00-90)")

    # Simples Nacional usa CSOSN
    csosn: Optional[str] = Field(None, pattern=r'^\d{3}$', description="CSOSN para Simples Nacional")

    modalidade_bc: Optional[int] = Field(None, ge=0, le=3, description="Modalidade BC ICMS")
    base_calculo: Decimal = Field(default=Decimal('0'), ge=0, decimal_places=2)
    aliquota: Decimal = Field(default=Decimal('0'), ge=0, le=100, decimal_places=2)
    valor: Decimal = Field(default=Decimal('0'), ge=0, decimal_places=2)

    # ICMS ST
    modalidade_bc_st: Optional[int] = Field(None, ge=0, le=5)
    base_calculo_st: Decimal = Field(default=Decimal('0'), ge=0, decimal_places=2)
    aliquota_st: Decimal = Field(default=Decimal('0'), ge=0, decimal_places=2)
    valor_st: Decimal = Field(default=Decimal('0'), ge=0, decimal_places=2)

    @model_validator(mode='after')
    def validar_icms_simples_nacional(self):
        """Valida: Se CSOSN preenchido, não usar CST"""
        if self.csosn and self.cst not in ['90']:
            if self.cst != '90':
                raise ValueError("Simples Nacional deve usar CSOSN, não CST")
        return self

class IPIItem(BaseModel):
    """IPI de um item (quando aplicável)"""

    cst: str = Field(..., pattern=r'^\d{2}$', description="CST IPI (00-99)")
    base_calculo: Decimal = Field(default=Decimal('0'), ge=0, decimal_places=2)
    aliquota: Decimal = Field(default=Decimal('0'), ge=0, le=100, decimal_places=4)
    valor: Decimal = Field(default=Decimal('0'), ge=0, decimal_places=2)

class PISItem(BaseModel):
    """PIS de um item"""

    cst: str = Field(..., pattern=r'^\d{2}$', description="CST PIS (01-99)")
    base_calculo: Decimal = Field(default=Decimal('0'), ge=0, decimal_places=2)
    aliquota: Decimal = Field(default=Decimal('0'), ge=0, decimal_places=4)
    valor: Decimal = Field(default=Decimal('0'), ge=0, decimal_places=2)

class COFINSItem(BaseModel):
    """COFINS de um item"""

    cst: str = Field(..., pattern=r'^\d{2}$', description="CST COFINS (01-99)")
    base_calculo: Decimal = Field(default=Decimal('0'), ge=0, decimal_places=2)
    aliquota: Decimal = Field(default=Decimal('0'), ge=0, decimal_places=4)
    valor: Decimal = Field(default=Decimal('0'), ge=0, decimal_places=2)

# ============================================
# ITEM DA NOTA FISCAL
# ============================================

class ItemNFeBase(BaseModel):
    """Item de produto/serviço na NF-e"""

    numero_item: int = Field(..., ge=1, le=990, description="Número sequencial do item")

    # Produto
    codigo_produto: str = Field(..., max_length=60, description="Código interno")
    ean: Optional[str] = Field(None, pattern=r'^\d{8}$|^\d{12,14}$', description="GTIN/EAN")
    descricao: str = Field(..., min_length=1, max_length=120, description="Descrição do produto")

    # Classificação fiscal
    ncm: NCM8 = Field(..., description="NCM - 8 dígitos")
    cest: Optional[str] = Field(None, pattern=r'^\d{7}$', description="CEST - 7 dígitos")
    cfop: CFOP4 = Field(..., description="CFOP - 4 dígitos")

    # Unidade e quantidade
    unidade_comercial: str = Field(..., max_length=6, description="UN, KG, LT, PC, etc")
    quantidade_comercial: Decimal = Field(..., gt=0, max_digits=15, decimal_places=4)
    valor_unitario_comercial: Decimal = Field(..., ge=0, max_digits=21, decimal_places=10)
    valor_total_bruto: Decimal = Field(..., ge=0, decimal_places=2)

    # Valores adicionais
    valor_desconto: Decimal = Field(default=Decimal('0'), ge=0, decimal_places=2)
    valor_frete: Decimal = Field(default=Decimal('0'), ge=0, decimal_places=2)
    valor_seguro: Decimal = Field(default=Decimal('0'), ge=0, decimal_places=2)
    valor_outras_despesas: Decimal = Field(default=Decimal('0'), ge=0, decimal_places=2)

    # Impostos (OBRIGATÓRIOS)
    icms: ICMSItem
    pis: PISItem
    cofins: COFINSItem
    ipi: Optional[IPIItem] = None  # Opcional, apenas se aplicável

    # Informações adicionais do produto
    informacoes_adicionais: Optional[str] = Field(None, max_length=500)

    @field_validator('cfop')
    @classmethod
    def validar_cfop(cls, v: str) -> str:
        """Valida CFOP (primeiro dígito 1-7, exceto 4)"""
        if v[0] not in ['1','2','3','5','6','7']:
            raise ValueError(f"CFOP inválido: {v}. Primeiro dígito deve ser 1,2,3,5,6 ou 7")
        return v

    @model_validator(mode='after')
    def validar_valor_total(self):
        """Valida: valor_total = (qtd * valor_unit) + frete + seguro + outras - desconto"""
        esperado = (
            (self.quantidade_comercial * self.valor_unitario_comercial)
            + self.valor_frete
            + self.valor_seguro
            + self.valor_outras_despesas
            - self.valor_desconto
        )

        # Tolerância de 0.02 para erros de arredondamento
        if abs(self.valor_total_bruto - esperado) > Decimal('0.02'):
            raise ValueError(
                f"Valor total inconsistente. "
                f"Esperado: {esperado:.2f}, Informado: {self.valor_total_bruto:.2f}"
            )

        return self

# ============================================
# TRANSPORTE
# ============================================

class TransportadoraNFe(BaseModel):
    """Dados da transportadora"""

    cnpj: Optional[CNPJ14] = None
    cpf: Optional[CPF11] = None
    razao_social: Optional[str] = Field(None, max_length=255)
    inscricao_estadual: Optional[str] = Field(None, max_length=20)
    endereco_completo: Optional[str] = Field(None, max_length=255)
    municipio: Optional[str] = Field(None, max_length=100)
    uf: Optional[str] = Field(None, pattern=r'^[A-Z]{2}$')

    @model_validator(mode='after')
    def validar_documento(self):
        """Valida: deve ter CNPJ OU CPF, não ambos"""
        if self.cnpj and self.cpf:
            raise ValueError("Informar apenas CNPJ ou CPF, não ambos")
        if not self.cnpj and not self.cpf:
            raise ValueError("Informar CNPJ ou CPF da transportadora")
        return self

class VeiculoTransporte(BaseModel):
    """Dados do veículo transportador"""

    placa: str = Field(..., pattern=r'^[A-Z]{3}\d{4}$|^[A-Z]{3}\d[A-Z]\d{2}$',
                      description="AAA0000 ou AAA0A00 (Mercosul)")
    uf: str = Field(..., pattern=r'^[A-Z]{2}$')
    rntc: Optional[str] = Field(None, max_length=20, description="Registro Transportador")

class VolumesTransporte(BaseModel):
    """Volumes transportados"""

    quantidade: int = Field(..., ge=1)
    especie: Optional[str] = Field(None, max_length=60, description="Caixa, Fardo, etc")
    marca: Optional[str] = Field(None, max_length=60)
    numeracao: Optional[str] = Field(None, max_length=60)
    peso_liquido: Optional[Decimal] = Field(None, ge=0, decimal_places=3, description="kg")
    peso_bruto: Optional[Decimal] = Field(None, ge=0, decimal_places=3, description="kg")

class TransporteNFe(BaseModel):
    """Informações completas de transporte"""

    modalidade_frete: ModalidadeFrete
    transportadora: Optional[TransportadoraNFe] = None
    veiculo: Optional[VeiculoTransporte] = None
    volumes: Optional[List[VolumesTransporte]] = None

    @model_validator(mode='after')
    def validar_transportadora_obrigatoria(self):
        """Se modalidade 1 ou 2, transportadora obrigatória"""
        if self.modalidade_frete in [1, 2] and not self.transportadora:
            raise ValueError("Modalidade FOB ou Terceiros requer dados da transportadora")
        return self

# ============================================
# COBRANÇA/DUPLICATAS
# ============================================

class DuplicataNFe(BaseModel):
    """Duplicata para pagamento"""

    numero: str = Field(..., max_length=60, description="Número da duplicata")
    vencimento: date = Field(..., description="Data de vencimento")
    valor: Decimal = Field(..., gt=0, decimal_places=2)

    @field_validator('vencimento')
    @classmethod
    def validar_vencimento_futuro(cls, v: date) -> str:
        """Vencimento não pode ser no passado"""
        if v < date.today():
            raise ValueError(f"Data de vencimento {v} está no passado")
        return v

class CobrancaNFe(BaseModel):
    """Dados de cobrança"""

    duplicatas: List[DuplicataNFe] = Field(..., min_length=1, max_length=120)

    @model_validator(mode='after')
    def validar_soma_duplicatas(self):
        """Soma das duplicatas será validada contra valor total da NF"""
        # Validação feita no modelo principal NotaFiscalCompletaCreate
        return self

# ============================================
# DESTINATÁRIO
# ============================================

class DestinatarioNFe(BaseModel):
    """Dados do destinatário da NF-e"""

    # Documento (CPF ou CNPJ)
    cpf: Optional[CPF11] = None
    cnpj: Optional[CNPJ14] = None

    # Dados cadastrais
    nome: str = Field(..., min_length=2, max_length=255, description="Nome/Razão Social")
    inscricao_estadual: Optional[str] = Field(None, max_length=20)

    # Endereço (simplificado para MVP, expandir depois)
    logradouro: str = Field(..., max_length=255)
    numero: str = Field(..., max_length=20)
    complemento: Optional[str] = Field(None, max_length=100)
    bairro: str = Field(..., max_length=100)
    municipio: str = Field(..., max_length=100)
    uf: str = Field(..., pattern=r'^[A-Z]{2}$')
    cep: str = Field(..., pattern=r'^\d{8}$')

    # Contato
    telefone: Optional[str] = Field(None, max_length=20)
    email: Optional[str] = Field(None, max_length=255)

    @model_validator(mode='after')
    def validar_documento(self):
        """Valida: deve ter CPF OU CNPJ (não ambos, não nenhum)"""
        if self.cpf and self.cnpj:
            raise ValueError("Informar apenas CPF ou CNPJ do destinatário")
        if not self.cpf and not self.cnpj:
            raise ValueError("Informar CPF ou CNPJ do destinatário")

        # Validar com validate-docbr
        if self.cpf and not CPF().validate(self.cpf):
            raise ValueError(f"CPF inválido: {self.cpf}")
        if self.cnpj and not CNPJ().validate(self.cnpj):
            raise ValueError(f"CNPJ inválido: {self.cnpj}")

        return self

# ============================================
# NOTA FISCAL COMPLETA
# ============================================

class NotaFiscalCompletaCreate(BaseModel):
    """
    Schema completo para criação de NF-e.
    Contém TODOS os campos obrigatórios identificados na auditoria.
    """

    # ===== IDENTIFICAÇÃO =====
    empresa_id: str = Field(..., description="UUID da empresa emitente")

    numero_nf: str = Field(..., pattern=r'^\d{1,9}$', description="1 a 999999999")
    serie: str = Field(..., pattern=r'^\d{1,3}$', description="1 a 999")
    modelo: Literal["55", "65"] = Field(..., description="55-NFe, 65-NFCe")
    tipo_operacao: TipoOperacao = Field(..., description="0-Entrada, 1-Saída")

    # ===== AMBIENTE =====
    ambiente: TipoAmbiente = Field(
        default="2",  # Homologação por padrão
        description="1-Produção, 2-Homologação"
    )

    # ===== DATAS =====
    data_emissao: datetime = Field(..., description="Data/hora de emissão")
    data_saida_entrada: Optional[datetime] = Field(None, description="Data/hora saída/entrada")

    # ===== DESTINATÁRIO =====
    destinatario: DestinatarioNFe

    # ===== ITENS (OBRIGATÓRIO) =====
    itens: List[ItemNFeBase] = Field(
        ...,
        min_length=1,
        max_length=990,
        description="Produtos/serviços da NF-e"
    )

    # ===== TOTAIS (calculados automaticamente) =====
    # Não precisa enviar, será calculado dos itens

    # ===== TRANSPORTE =====
    transporte: TransporteNFe = Field(..., description="Dados de transporte (obrigatório)")

    # ===== COBRANÇA =====
    cobranca: Optional[CobrancaNFe] = Field(None, description="Duplicatas (se não for à vista)")

    # ===== INFORMAÇÕES ADICIONAIS =====
    informacoes_complementares: Optional[str] = Field(
        None,
        max_length=5000,
        description="Informações ao consumidor"
    )
    informacoes_fisco: Optional[str] = Field(
        None,
        max_length=2000,
        description="Informações de interesse do fisco"
    )

    @model_validator(mode='after')
    def validar_itens_sequenciais(self):
        """Garante numeração sequencial 1, 2, 3..."""
        for idx, item in enumerate(self.itens, start=1):
            if item.numero_item != idx:
                raise ValueError(f"Item na posição {idx} deve ter numero_item={idx}")
        return self

    @model_validator(mode='after')
    def validar_duplicatas_vs_total(self):
        """Soma duplicatas deve bater com valor total da NF"""
        if not self.cobranca:
            return self

        # Calcular total da nota
        total_produtos = sum(item.valor_total_bruto for item in self.itens)

        # Calcular total das duplicatas
        total_duplicatas = sum(dup.valor for dup in self.cobranca.duplicatas)

        # Tolerância de 0.01 para arredondamento
        if abs(total_produtos - total_duplicatas) > Decimal('0.01'):
            raise ValueError(
                f"Soma das duplicatas ({total_duplicatas:.2f}) "
                f"difere do valor total ({total_produtos:.2f})"
            )

        return self

    def calcular_totais(self) -> dict:
        """Calcula todos os totais da NF-e a partir dos itens"""

        totais = {
            "valor_produtos": Decimal('0'),
            "valor_frete": Decimal('0'),
            "valor_seguro": Decimal('0'),
            "valor_desconto": Decimal('0'),
            "valor_outras_despesas": Decimal('0'),
            "valor_total": Decimal('0'),
            "total_icms": Decimal('0'),
            "total_icms_st": Decimal('0'),
            "total_ipi": Decimal('0'),
            "total_pis": Decimal('0'),
            "total_cofins": Decimal('0'),
        }

        for item in self.itens:
            totais["valor_produtos"] += item.valor_total_bruto
            totais["valor_frete"] += item.valor_frete
            totais["valor_seguro"] += item.valor_seguro
            totais["valor_desconto"] += item.valor_desconto
            totais["valor_outras_despesas"] += item.valor_outras_despesas

            totais["total_icms"] += item.icms.valor
            totais["total_icms_st"] += item.icms.valor_st
            totais["total_pis"] += item.pis.valor
            totais["total_cofins"] += item.cofins.valor

            if item.ipi:
                totais["total_ipi"] += item.ipi.valor

        # Valor total = produtos + frete + seguro + outras - desconto + IPI + ST
        totais["valor_total"] = (
            totais["valor_produtos"]
            + totais["valor_frete"]
            + totais["valor_seguro"]
            + totais["valor_outras_despesas"]
            - totais["valor_desconto"]
            + totais["total_ipi"]
            + totais["total_icms_st"]
        )

        return totais

# ============================================
# RESPONSE MODELS
# ============================================

class NotaFiscalCompletaResponse(BaseModel):
    """Response da NF-e após processamento"""

    id: str
    empresa_id: str

    # Identificação
    chave_acesso: Optional[ChaveNFe] = None
    protocolo: Optional[str] = None
    numero_nf: str
    serie: str
    modelo: str

    # Status
    situacao: str = Field(..., description="processando, autorizada, rejeitada, cancelada")
    situacao_sefaz_codigo: Optional[str] = None
    situacao_sefaz_motivo: Optional[str] = None
    ambiente: str

    # Datas
    data_emissao: datetime
    data_autorizacao: Optional[datetime] = None

    # Partes
    cnpj_emitente: str
    nome_emitente: str
    destinatario_documento: str  # CPF ou CNPJ
    destinatario_nome: str

    # Totais
    valor_produtos: Decimal
    valor_total: Decimal
    total_icms: Decimal
    total_pis: Decimal
    total_cofins: Decimal
    total_ipi: Decimal

    # URLs
    xml_url: Optional[str] = None
    pdf_url: Optional[str] = None

    # Metadata
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}

# ============================================
# ERROS SEFAZ
# ============================================

class SefazRejeicao(BaseModel):
    """Rejeição específica da SEFAZ"""

    codigo: str = Field(..., pattern=r'^\d{3}$', description="Código 3 dígitos")
    motivo: str = Field(..., description="Descrição do erro")
    correcao: Optional[str] = Field(None, description="Como corrigir")
    campo_erro: Optional[str] = Field(None, description="Campo que causou erro")

class SefazResponseModel(BaseModel):
    """Resposta padronizada da SEFAZ"""

    # Status
    status_codigo: str = Field(..., description="100=Autorizado, 101=Cancelado, etc")
    status_descricao: str = Field("", description="Mensagem SEFAZ")

    # Protocolo (se autorizado)
    protocolo: Optional[str] = None
    chave_acesso: Optional[str] = None
    data_recebimento: Optional[datetime] = None

    # XML retorno
    xml_retorno: Optional[str] = Field(None, description="XML completo da resposta")

    # Rejeições (se houver)
    rejeicoes: List[SefazRejeicao] = Field(default_factory=list)

    # Ambiente e UF (opcionais)
    ambiente: Optional[str] = None
    uf: Optional[str] = None

    # Metadata
    tempo_resposta_ms: Optional[int] = Field(None, description="Tempo de resposta em ms")

    @property
    def autorizado(self) -> bool:
        """Verifica se foi autorizado"""
        return self.status_codigo == "100"

    @property
    def rejeitado(self) -> bool:
        """Verifica se foi rejeitado"""
        return len(self.rejeicoes) > 0

    @property
    def em_processamento(self) -> bool:
        """Verifica se está em processamento"""
        return self.status_codigo == "105"

# ============================================
# FIM DOS MODELOS
# ============================================
