"""
Utilidades para manipulação de XML de NF-e e SEFAZ.

Funções auxiliares para extrair informações de XMLs SEFAZ,
validar estruturas e processar respostas.
"""
from typing import Optional, Dict, List
import logging

try:
    from lxml import etree
except ImportError:
    etree = None

logger = logging.getLogger(__name__)

# Namespaces comuns
NAMESPACE_NFE = "http://www.portalfiscal.inf.br/nfe"
NAMESPACE_SIG = "http://www.w3.org/2000/09/xmldsig#"


def extrair_chave_acesso(xml_string: str) -> Optional[str]:
    """
    Extrai chave de acesso de 44 dígitos do XML.

    Args:
        xml_string: XML completo da NF-e ou resposta SEFAZ

    Returns:
        Chave de 44 dígitos ou None
    """
    if etree is None:
        logger.error("lxml não disponível")
        return None

    try:
        root = etree.fromstring(xml_string.encode('utf-8'))

        # Tentar vários caminhos possíveis
        caminhos = [
            './/chNFe',
            './/chave',
            './/{*}chNFe',
            './/{*}chave',
        ]

        for caminho in caminhos:
            elem = root.find(caminho)
            if elem is not None and elem.text:
                chave = elem.text.strip()
                if len(chave) == 44 and chave.isdigit():
                    return chave

        return None

    except Exception as e:
        logger.error(f"Erro ao extrair chave de acesso: {e}")
        return None


def extrair_protocolo(xml_string: str) -> Optional[str]:
    """
    Extrai número de protocolo do XML de resposta SEFAZ.

    Args:
        xml_string: XML de resposta SEFAZ

    Returns:
        Número do protocolo ou None
    """
    if etree is None:
        return None

    try:
        root = etree.fromstring(xml_string.encode('utf-8'))

        caminhos = [
            './/nProt',
            './/{*}nProt',
            './/protocolo',
        ]

        for caminho in caminhos:
            elem = root.find(caminho)
            if elem is not None and elem.text:
                return elem.text.strip()

        return None

    except Exception as e:
        logger.error(f"Erro ao extrair protocolo: {e}")
        return None


def extrair_status_code(xml_string: str) -> Optional[str]:
    """
    Extrai código de status da resposta SEFAZ.

    Args:
        xml_string: XML de resposta SEFAZ

    Returns:
        Código de status (ex: '100', '204', etc) ou None
    """
    if etree is None:
        return None

    try:
        root = etree.fromstring(xml_string.encode('utf-8'))

        caminhos = [
            './/cStat',
            './/{*}cStat',
            './/status',
        ]

        for caminho in caminhos:
            elem = root.find(caminho)
            if elem is not None and elem.text:
                return elem.text.strip()

        return None

    except Exception as e:
        logger.error(f"Erro ao extrair status code: {e}")
        return None


def extrair_motivo(xml_string: str) -> Optional[str]:
    """
    Extrai motivo/mensagem da resposta SEFAZ.

    Args:
        xml_string: XML de resposta SEFAZ

    Returns:
        Mensagem de retorno ou None
    """
    if etree is None:
        return None

    try:
        root = etree.fromstring(xml_string.encode('utf-8'))

        caminhos = [
            './/xMotivo',
            './/{*}xMotivo',
            './/mensagem',
            './/motivo',
        ]

        for caminho in caminhos:
            elem = root.find(caminho)
            if elem is not None and elem.text:
                return elem.text.strip()

        return None

    except Exception as e:
        logger.error(f"Erro ao extrair motivo: {e}")
        return None


def extrair_rejeicoes(xml_string: str) -> List[Dict[str, str]]:
    """
    Extrai lista de rejeições do XML de resposta SEFAZ.

    Args:
        xml_string: XML de resposta SEFAZ

    Returns:
        Lista de dicts com {codigo, motivo}
    """
    if etree is None:
        return []

    rejeicoes = []

    try:
        root = etree.fromstring(xml_string.encode('utf-8'))

        # Procurar elementos de rejeição
        for elem_rej in root.findall('.//{*}infProt'):
            codigo_elem = elem_rej.find('.//{*}cStat')
            motivo_elem = elem_rej.find('.//{*}xMotivo')

            if codigo_elem is not None and codigo_elem.text:
                codigo = codigo_elem.text.strip()

                # Códigos de sucesso não são rejeições
                if codigo in ['100', '101', '102', '135', '150', '151']:
                    continue

                motivo = motivo_elem.text.strip() if motivo_elem is not None else 'Sem descrição'

                rejeicoes.append({
                    'codigo': codigo,
                    'motivo': motivo,
                })

        return rejeicoes

    except Exception as e:
        logger.error(f"Erro ao extrair rejeições: {e}")
        return []


def validar_xml_bem_formado(xml_string: str) -> bool:
    """
    Valida se XML está bem formado (sintaxe correta).

    Args:
        xml_string: XML para validar

    Returns:
        True se válido, False caso contrário
    """
    if etree is None:
        logger.warning("lxml não disponível - pulando validação")
        return True

    try:
        etree.fromstring(xml_string.encode('utf-8'))
        return True
    except etree.XMLSyntaxError as e:
        logger.error(f"XML mal formado: {e}")
        return False
    except Exception as e:
        logger.error(f"Erro ao validar XML: {e}")
        return False


def extrair_data_recebimento(xml_string: str) -> Optional[str]:
    """
    Extrai data/hora de recebimento do XML SEFAZ.

    Args:
        xml_string: XML de resposta SEFAZ

    Returns:
        Data/hora em formato ISO ou None
    """
    if etree is None:
        return None

    try:
        root = etree.fromstring(xml_string.encode('utf-8'))

        caminhos = [
            './/dhRecbto',
            './/{*}dhRecbto',
            './/dataRecebimento',
        ]

        for caminho in caminhos:
            elem = root.find(caminho)
            if elem is not None and elem.text:
                return elem.text.strip()

        return None

    except Exception as e:
        logger.error(f"Erro ao extrair data recebimento: {e}")
        return None


def parsear_resposta_completa(xml_string: str) -> Dict[str, any]:
    """
    Parse completo de resposta SEFAZ extraindo todos os campos relevantes.

    Args:
        xml_string: XML de resposta SEFAZ

    Returns:
        Dict com todos os campos extraídos
    """
    return {
        'chave_acesso': extrair_chave_acesso(xml_string),
        'protocolo': extrair_protocolo(xml_string),
        'status_codigo': extrair_status_code(xml_string),
        'motivo': extrair_motivo(xml_string),
        'data_recebimento': extrair_data_recebimento(xml_string),
        'rejeicoes': extrair_rejeicoes(xml_string),
        'xml_valido': validar_xml_bem_formado(xml_string),
    }


# ============================================
# FUNÇÕES PARA DISTRIBUICAODFE (BUSCA DE NOTAS)
# ============================================

def extrair_cnpj_emitente(xml_string: str) -> Optional[str]:
    """
    Extrai CNPJ do emitente de um resNFe ou NFe completa.

    Args:
        xml_string: XML resNFe ou NFe completa

    Returns:
        CNPJ de 14 dígitos ou None
    """
    if etree is None:
        return None

    try:
        root = etree.fromstring(xml_string.encode('utf-8'))

        # Caminhos possíveis
        caminhos = [
            './/CNPJEmit',  # resNFe
            './/{*}CNPJEmit',
            './/emit/CNPJ',  # NFe completa
            './/{*}emit/{*}CNPJ',
        ]

        for caminho in caminhos:
            elem = root.find(caminho)
            if elem is not None and elem.text:
                cnpj = elem.text.strip()
                if len(cnpj) == 14 and cnpj.isdigit():
                    return cnpj

        return None

    except Exception as e:
        logger.error(f"Erro ao extrair CNPJ emitente: {e}")
        return None


def extrair_cnpj_destinatario(xml_string: str) -> Optional[str]:
    """
    Extrai CNPJ do destinatário de um resNFe ou NFe completa.

    Args:
        xml_string: XML resNFe ou NFe completa

    Returns:
        CNPJ de 14 dígitos ou None
    """
    if etree is None:
        return None

    try:
        root = etree.fromstring(xml_string.encode('utf-8'))

        caminhos = [
            './/CNPJDest',  # resNFe
            './/{*}CNPJDest',
            './/dest/CNPJ',  # NFe completa
            './/{*}dest/{*}CNPJ',
        ]

        for caminho in caminhos:
            elem = root.find(caminho)
            if elem is not None and elem.text:
                cnpj = elem.text.strip()
                if len(cnpj) == 14 and cnpj.isdigit():
                    return cnpj

        return None

    except Exception as e:
        logger.error(f"Erro ao extrair CNPJ destinatário: {e}")
        return None


def extrair_cpf_destinatario(xml_string: str) -> Optional[str]:
    """
    Extrai CPF do destinatário de um resNFe ou NFe completa.

    Args:
        xml_string: XML resNFe ou NFe completa

    Returns:
        CPF de 11 dígitos ou None
    """
    if etree is None:
        return None

    try:
        root = etree.fromstring(xml_string.encode('utf-8'))

        caminhos = [
            './/CPFDest',  # resNFe
            './/{*}CPFDest',
            './/dest/CPF',  # NFe completa
            './/{*}dest/{*}CPF',
        ]

        for caminho in caminhos:
            elem = root.find(caminho)
            if elem is not None and elem.text:
                cpf = elem.text.strip()
                if len(cpf) == 11 and cpf.isdigit():
                    return cpf

        return None

    except Exception as e:
        logger.error(f"Erro ao extrair CPF destinatário: {e}")
        return None


def extrair_valor_total(xml_string: str) -> Optional[str]:
    """
    Extrai valor total da NFe de um resNFe ou NFe completa.

    Args:
        xml_string: XML resNFe ou NFe completa

    Returns:
        Valor total como string ou None
    """
    if etree is None:
        return None

    try:
        root = etree.fromstring(xml_string.encode('utf-8'))

        caminhos = [
            './/vNF',  # resNFe
            './/{*}vNF',
            './/total/ICMSTot/vNF',  # NFe completa
            './/{*}total/{*}ICMSTot/{*}vNF',
        ]

        for caminho in caminhos:
            elem = root.find(caminho)
            if elem is not None and elem.text:
                return elem.text.strip()

        return None

    except Exception as e:
        logger.error(f"Erro ao extrair valor total: {e}")
        return None


def extrair_nsu(xml_string: str) -> Optional[int]:
    """
    Extrai NSU (Número Sequencial Único) do resNFe.

    Args:
        xml_string: XML resNFe

    Returns:
        NSU como inteiro ou None
    """
    if etree is None:
        return None

    try:
        root = etree.fromstring(xml_string.encode('utf-8'))

        caminhos = [
            './/NSU',
            './/{*}NSU',
        ]

        for caminho in caminhos:
            elem = root.find(caminho)
            if elem is not None and elem.text:
                try:
                    return int(elem.text.strip())
                except ValueError:
                    continue

        return None

    except Exception as e:
        logger.error(f"Erro ao extrair NSU: {e}")
        return None


def extrair_nome_emitente(xml_string: str) -> Optional[str]:
    """
    Extrai nome/razão social do emitente.

    Args:
        xml_string: XML resNFe ou NFe completa

    Returns:
        Nome do emitente ou None
    """
    if etree is None:
        return None

    try:
        root = etree.fromstring(xml_string.encode('utf-8'))

        caminhos = [
            './/xNomeEmit',  # resNFe
            './/{*}xNomeEmit',
            './/emit/xNome',  # NFe completa
            './/{*}emit/{*}xNome',
        ]

        for caminho in caminhos:
            elem = root.find(caminho)
            if elem is not None and elem.text:
                return elem.text.strip()

        return None

    except Exception as e:
        logger.error(f"Erro ao extrair nome emitente: {e}")
        return None


def extrair_nome_destinatario(xml_string: str) -> Optional[str]:
    """
    Extrai nome/razão social do destinatário.

    Args:
        xml_string: XML resNFe ou NFe completa

    Returns:
        Nome do destinatário ou None
    """
    if etree is None:
        return None

    try:
        root = etree.fromstring(xml_string.encode('utf-8'))

        caminhos = [
            './/xNomeDest',  # resNFe
            './/{*}xNomeDest',
            './/dest/xNome',  # NFe completa
            './/{*}dest/{*}xNome',
        ]

        for caminho in caminhos:
            elem = root.find(caminho)
            if elem is not None and elem.text:
                return elem.text.strip()

        return None

    except Exception as e:
        logger.error(f"Erro ao extrair nome destinatário: {e}")
        return None


def extrair_situacao_nfe(xml_string: str) -> Optional[str]:
    """
    Extrai código de situação da NFe (cSitNFe).

    Args:
        xml_string: XML resNFe

    Returns:
        Código situação (1, 2, 3) ou None
    """
    if etree is None:
        return None

    try:
        root = etree.fromstring(xml_string.encode('utf-8'))

        caminhos = [
            './/cSitNFe',
            './/{*}cSitNFe',
        ]

        for caminho in caminhos:
            elem = root.find(caminho)
            if elem is not None and elem.text:
                return elem.text.strip()

        return None

    except Exception as e:
        logger.error(f"Erro ao extrair situação NFe: {e}")
        return None


def extrair_data_emissao(xml_string: str) -> Optional[str]:
    """
    Extrai data/hora de emissão da NFe.

    Args:
        xml_string: XML resNFe ou NFe completa

    Returns:
        Data emissão em formato ISO ou None
    """
    if etree is None:
        return None

    try:
        root = etree.fromstring(xml_string.encode('utf-8'))

        caminhos = [
            './/dhEmi',  # resNFe
            './/{*}dhEmi',
            './/ide/dhEmi',  # NFe completa
            './/{*}ide/{*}dhEmi',
        ]

        for caminho in caminhos:
            elem = root.find(caminho)
            if elem is not None and elem.text:
                return elem.text.strip()

        return None

    except Exception as e:
        logger.error(f"Erro ao extrair data emissão: {e}")
        return None


def extrair_tipo_operacao(xml_string: str) -> Optional[str]:
    """
    Extrai tipo de operação da NFe (tpNF).

    Args:
        xml_string: XML resNFe ou NFe completa

    Returns:
        "0" (entrada) ou "1" (saída) ou None
    """
    if etree is None:
        return None

    try:
        root = etree.fromstring(xml_string.encode('utf-8'))

        caminhos = [
            './/tpNF',
            './/{*}tpNF',
            './/ide/tpNF',
            './/{*}ide/{*}tpNF',
        ]

        for caminho in caminhos:
            elem = root.find(caminho)
            if elem is not None and elem.text:
                tipo = elem.text.strip()
                if tipo in ['0', '1']:
                    return tipo

        return None

    except Exception as e:
        logger.error(f"Erro ao extrair tipo operação: {e}")
        return None

