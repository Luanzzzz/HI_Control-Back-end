"""
Serviço de mapeamento entre modelos de NFe buscada e Nota Fiscal do banco.

Converte NFeBuscadaMetadata (resultado do DistribuicaoDFe) 
para NotaFiscalCreate (modelo do banco de dados).
"""
from app.models.nfe_busca import NFeBuscadaMetadata
from app.models.nota_fiscal import NotaFiscalCreate
from decimal import Decimal
import logging

logger = logging.getLogger(__name__)


def map_nfe_buscada_to_nota_fiscal(
    nfe: NFeBuscadaMetadata,
    empresa_id: str
) -> NotaFiscalCreate:
    """
    Converte NFeBuscadaMetadata para NotaFiscalCreate.
    
    Aplica validação defensiva e extrai dados da chave de acesso.
    
    Args:
        nfe: Metadados da NFe do DistribuicaoDFe
        empresa_id: UUID da empresa no banco
    
    Returns:
        NotaFiscalCreate pronto para persistência
    
    Raises:
        ValueError: Se chave de acesso inválida
    """
    # Validação defensiva: garantir 44 caracteres
    if not nfe.chave_acesso or len(nfe.chave_acesso) != 44:
        raise ValueError(
            f"Chave de acesso inválida: esperado 44 caracteres, "
            f"recebido {len(nfe.chave_acesso) if nfe.chave_acesso else 0}"
        )
    
    if not nfe.chave_acesso.isdigit():
        raise ValueError("Chave de acesso deve conter apenas dígitos")
    
    # Extrair informações da chave de acesso
    numero_nf = extrair_numero_da_chave(nfe.chave_acesso)
    serie = extrair_serie_da_chave(nfe.chave_acesso)
    
    # Mapear situação
    situacao_map = {
        "1": "autorizada",
        "2": "denegada",
        "3": "cancelada",
    }
    situacao = situacao_map.get(nfe.situacao_codigo, nfe.situacao)
    
    return NotaFiscalCreate(
        empresa_id=empresa_id,
        numero_nf=numero_nf,
        serie=serie,
        tipo_nf="NFe",
        modelo="55",
        chave_acesso=nfe.chave_acesso,
        data_emissao=nfe.data_emissao,
        data_autorizacao=nfe.data_emissao,  # Usar data_emissao como aproximação
        valor_total=nfe.valor_total,
        valor_produtos=nfe.valor_total,  # Aproximação (resNFe não detalha)
        cnpj_emitente=nfe.cnpj_emitente,
        nome_emitente=nfe.nome_emitente,
        cnpj_destinatario=nfe.cnpj_destinatario,
        nome_destinatario=nfe.nome_destinatario,
        situacao=situacao,
        protocolo=nfe.protocolo,
        observacoes=f"Importada via DistribuicaoDFe | NSU: {nfe.nsu}"
    )


def extrair_numero_da_chave(chave: str) -> str:
    """
    Extrai número da NF da chave de acesso.
    
    Posições 25-33 (9 dígitos).
    Remove zeros à esquerda para formato legível.
    
    Args:
        chave: Chave de acesso de 44 dígitos
    
    Returns:
        Número da NF como string
    """
    numero_raw = chave[25:34]  # Posições 25-33 (9 caracteres)
    return str(int(numero_raw))  # Remove zeros à esquerda


def extrair_serie_da_chave(chave: str) -> str:
    """
    Extrai série da NF da chave de acesso.
    
    Posições 22-24 (3 dígitos).
    Remove zeros à esquerda.
    
    Args:
        chave: Chave de acesso de 44 dígitos
    
    Returns:
        Série da NF como string
    """
    serie_raw = chave[22:25]  # Posições 22-24 (3 caracteres)
    return str(int(serie_raw))  # Remove zeros à esquerda


def extrair_uf_da_chave(chave: str) -> str:
    """
    Extrai código da UF da chave de acesso.
    
    Posições 0-1 (2 dígitos).
    
    Args:
        chave: Chave de acesso de 44 dígitos
    
    Returns:
        Código UF (ex: "35" para SP)
    """
    return chave[0:2]


def validar_chave_acesso(chave: str) -> bool:
    """
    Valida estrutura básica da chave de acesso.

    Args:
        chave: Chave a validar

    Returns:
        True se válida, False caso contrário
    """
    if not chave or len(chave) != 44:
        return False

    if not chave.isdigit():
        return False

    return True


def extrair_modelo_da_chave(chave: str) -> str:
    """
    Extrai o modelo da NFe da chave de acesso (posições 20-21).

    Args:
        chave: Chave de acesso de 44 dígitos

    Returns:
        str: Código do modelo (ex: "55" para NFe, "65" para NFCe)

    Raises:
        ValueError: Se chave inválida

    Examples:
        >>> extrair_modelo_da_chave("35241111222333000199550010000123451234567890")
        "55"
    """
    if not chave or len(chave) != 44:
        raise ValueError(f"Chave de acesso inválida (deve ter 44 dígitos): {chave}")

    modelo_raw = chave[20:22]

    if not modelo_raw.isdigit():
        raise ValueError(f"Modelo inválido na chave: {modelo_raw}")

    return modelo_raw


def modelo_to_tipo_nf(modelo: str, tipo_operacao: str) -> str:
    """
    Converte código do modelo e tipo de operação em tipo de NFe.

    Args:
        modelo: Código do modelo ("55", "65", etc)
        tipo_operacao: "ENTRADA" ou "SAIDA"

    Returns:
        str: Tipo formatado (ex: "NFe Entrada", "NFCe Saída")

    Examples:
        >>> modelo_to_tipo_nf("55", "ENTRADA")
        "NFe Entrada"
        >>> modelo_to_tipo_nf("65", "SAIDA")
        "NFCe Saída"
    """
    modelos = {
        "55": "NFe",
        "65": "NFCe",
        "57": "CT-e",
        "58": "MDF-e",
    }

    tipo_doc = modelos.get(modelo, f"Modelo {modelo}")
    tipo_op = tipo_operacao.capitalize() if tipo_operacao else "Entrada"

    return f"{tipo_doc} {tipo_op}"


def gerar_id_from_chave(chave: str) -> str:
    """
    Gera um ID único para a nota baseado na chave de acesso.
    Usa os últimos 12 dígitos da chave (mais variáveis).

    Args:
        chave: Chave de acesso de 44 dígitos

    Returns:
        str: ID único (últimos 12 dígitos)

    Examples:
        >>> gerar_id_from_chave("35241111222333000199550010000123451234567890")
        "234567890"
    """
    if not chave or len(chave) != 44:
        return chave  # Fallback para chave completa se inválida

    # Usar últimos 12 dígitos (série + número + dígitos verificadores)
    return chave[-12:]
