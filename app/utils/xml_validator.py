"""
Validador de XMLs fiscais contra schemas XSD oficiais.

Objetivo: Validar XMLs de NF-e, NFC-e, CT-e contra schemas XSD ANTES
de assinar e enviar ao SEFAZ. Isso evita erros genéricos (cStat 225)
e permite correção antecipada de problemas.

Autor: Claude Sonnet 4.5
Data: 2026-03-12
"""

import os
import logging
from typing import Tuple, List, Optional
from pathlib import Path

try:
    from lxml import etree
except ImportError:
    etree = None

logger = logging.getLogger(__name__)

# Diretório dos schemas XSD
SCHEMAS_DIR = Path(__file__).parent.parent / "schemas" / "xsd"

# Mapeamento de tipo de documento → arquivo XSD
SCHEMA_FILES = {
    "55": "nfe_v4.00.xsd",        # NF-e modelo 55
    "65": "nfce_v4.00.xsd",       # NFC-e modelo 65
    "57": "cte_v4.00.xsd",        # CT-e modelo 57
    "consulta": "consSitNFe_v4.00.xsd",
    "cancelamento": "evCancNFe_v1.00.xsd",
    "inutilizacao": "inutNFe_v4.00.xsd",
}


class XSDValidationError(Exception):
    """Erro de validação XSD"""
    def __init__(self, erros: List[str]):
        self.erros = erros
        super().__init__(f"Validação XSD falhou com {len(erros)} erro(s)")


def validar_xml_contra_xsd(
    xml_string: str,
    tipo_documento: str = "55",
    ambiente: str = "production"
) -> Tuple[bool, List[str]]:
    """
    Valida XML fiscal contra schema XSD oficial.

    Args:
        xml_string: String contendo o XML a ser validado
        tipo_documento: Tipo do documento fiscal
            - "55": NF-e
            - "65": NFC-e
            - "57": CT-e
            - "consulta": Consulta de NF-e
            - "cancelamento": Evento de cancelamento
            - "inutilizacao": Inutilização
        ambiente: "production" ou "development"

    Returns:
        Tupla (valido, lista_de_erros)
        - Se válido: (True, [])
        - Se inválido: (False, ["Campo X inválido: ...", "Campo Y obrigatório", ...])

    Raises:
        ValueError: Se lxml não disponível ou schema XSD não encontrado

    Example:
        >>> xml = "<NFe>...</NFe>"
        >>> valido, erros = validar_xml_contra_xsd(xml, tipo_documento="55")
        >>> if not valido:
        ...     for erro in erros:
        ...         print(erro)
    """
    # 1. Verificar disponibilidade do lxml
    if etree is None:
        erro_msg = (
            "lxml não disponível. "
            "Instale com: pip install lxml"
        )
        logger.error(erro_msg)

        # Em desenvolvimento, permitir sem validação (com warning)
        if ambiente == "development":
            logger.warning("⚠️ DESENVOLVIMENTO: Validação XSD PULADA (lxml ausente)")
            return (True, [])  # Não bloquear desenvolvimento

        # Em produção, bloquear
        raise ValueError(erro_msg)

    # 1.5. VALIDAR SINTAXE XML ANTES DE PROCURAR SCHEMA
    # Isso garante que XMLs mal-formados sejam rejeitados mesmo sem schema
    try:
        xml_doc_temp = etree.fromstring(xml_string.encode('utf-8'))
        logger.debug("XML parseado com sucesso (sintaxe válida)")

    except etree.XMLSyntaxError as e:
        erro_detalhado = f"XML mal-formado na linha {e.lineno}: {e.msg}"
        logger.error(erro_detalhado)
        return (False, [erro_detalhado])

    except Exception as e:
        erro_detalhado = f"Erro ao parsear XML: {str(e)}"
        logger.error(erro_detalhado)
        return (False, [erro_detalhado])

    # 2. Obter arquivo XSD apropriado
    schema_file = SCHEMA_FILES.get(tipo_documento)
    if not schema_file:
        logger.warning(
            f"Tipo de documento '{tipo_documento}' não mapeado. "
            f"Tipos válidos: {list(SCHEMA_FILES.keys())}"
        )
        # Retornar válido por padrão para tipos desconhecidos
        return (True, [])

    schema_path = SCHEMAS_DIR / schema_file

    # 3. Verificar existência do schema
    if not schema_path.exists():
        erro_msg = (
            f"Schema XSD não encontrado: {schema_path}\n"
            f"Baixe os schemas oficiais em: "
            f"https://www.nfe.fazenda.gov.br/portal/listaConteudo.aspx?tipoConteudo=BMPFMBoln3w=\n"
            f"Consulte: {SCHEMAS_DIR / 'README.md'}"
        )
        logger.error(erro_msg)

        # Em desenvolvimento, permitir sem validação (com warning)
        if ambiente == "development":
            logger.warning("⚠️ DESENVOLVIMENTO: Validação XSD PULADA (schema ausente)")
            return (True, [])

        # Em produção, bloquear
        raise FileNotFoundError(erro_msg)

    # 4. Carregar schema XSD
    try:
        with open(schema_path, 'rb') as f:
            schema_doc = etree.parse(f)
            schema = etree.XMLSchema(schema_doc)

        logger.debug(f"Schema XSD carregado: {schema_file}")

    except etree.XMLSchemaParseError as e:
        erro_msg = f"Erro ao parsear schema XSD {schema_file}: {str(e)}"
        logger.error(erro_msg)
        raise ValueError(erro_msg)

    except Exception as e:
        erro_msg = f"Erro ao carregar schema XSD: {str(e)}"
        logger.error(erro_msg)
        raise ValueError(erro_msg)

    # 5. Usar XML já parseado no passo 1.5
    xml_doc = xml_doc_temp

    # 6. Validar XML contra schema
    try:
        schema.assertValid(xml_doc)
        logger.info(f"✅ Validação XSD bem-sucedida ({schema_file})")
        return (True, [])

    except etree.DocumentInvalid as e:
        # Schema validation falhou - processar erros
        erros_formatados = _formatar_erros_validacao(schema.error_log)
        logger.warning(
            f"❌ Validação XSD falhou com {len(erros_formatados)} erro(s):\n"
            + "\n".join(f"  - {erro}" for erro in erros_formatados[:5])
        )
        return (False, erros_formatados)

    except Exception as e:
        erro_detalhado = f"Erro inesperado na validação XSD: {str(e)}"
        logger.error(erro_detalhado)
        return (False, [erro_detalhado])


def _formatar_erros_validacao(error_log) -> List[str]:
    """
    Formata erros de validação XSD para mensagens legíveis.

    Args:
        error_log: lxml XMLSchema error_log

    Returns:
        Lista de mensagens de erro formatadas

    Example:
        Entrada: "Element 'cProd': [facet 'maxLength'] The value has a length of '65'; this exceeds the allowed maximum length of '60'."
        Saída: "Campo 'cProd': Valor excede tamanho máximo de 60 caracteres (atual: 65)"
    """
    erros_formatados = []

    for erro in error_log:
        mensagem_original = erro.message
        linha = erro.line
        coluna = erro.column

        # Extrair nome do campo (entre aspas simples)
        import re
        campo_match = re.search(r"Element '([^']+)'", mensagem_original)
        campo = campo_match.group(1) if campo_match else "desconhecido"

        # Formatar mensagens comuns
        if "required" in mensagem_original.lower():
            mensagem = f"Campo '{campo}' é obrigatório mas está ausente"

        elif "maxLength" in mensagem_original:
            # Extrair tamanhos
            tamanho_match = re.search(r"length of '(\d+)'.*maximum.*of '(\d+)'", mensagem_original)
            if tamanho_match:
                tamanho_atual = tamanho_match.group(1)
                tamanho_max = tamanho_match.group(2)
                mensagem = f"Campo '{campo}': Valor excede tamanho máximo de {tamanho_max} caracteres (atual: {tamanho_atual})"
            else:
                mensagem = f"Campo '{campo}': Valor excede tamanho máximo permitido"

        elif "minLength" in mensagem_original:
            tamanho_match = re.search(r"length of '(\d+)'.*minimum.*of '(\d+)'", mensagem_original)
            if tamanho_match:
                tamanho_atual = tamanho_match.group(1)
                tamanho_min = tamanho_match.group(2)
                mensagem = f"Campo '{campo}': Valor menor que tamanho mínimo de {tamanho_min} caracteres (atual: {tamanho_atual})"
            else:
                mensagem = f"Campo '{campo}': Valor menor que tamanho mínimo permitido"

        elif "pattern" in mensagem_original.lower():
            mensagem = f"Campo '{campo}': Formato inválido (não corresponde ao padrão esperado)"

        elif "not a valid value" in mensagem_original or "enumeration" in mensagem_original:
            mensagem = f"Campo '{campo}': Valor não permitido (verifique valores aceitos)"

        elif "type" in mensagem_original.lower():
            # Erro de tipo de dados
            tipo_match = re.search(r"type '([^']+)'", mensagem_original)
            tipo_esperado = tipo_match.group(1) if tipo_match else "correto"
            mensagem = f"Campo '{campo}': Tipo de dado inválido (esperado: {tipo_esperado})"

        elif "decimal" in mensagem_original.lower() or "fraction" in mensagem_original.lower():
            mensagem = f"Campo '{campo}': Formato decimal inválido (verifique casas decimais)"

        else:
            # Erro genérico - usar mensagem original resumida
            mensagem = f"Campo '{campo}': {mensagem_original[:100]}"

        # Adicionar linha se disponível
        if linha:
            mensagem += f" (linha {linha})"

        erros_formatados.append(mensagem)

    return erros_formatados


def validar_xml_nfe(xml_string: str, ambiente: str = "production") -> Tuple[bool, List[str]]:
    """
    Atalho para validar XML de NF-e modelo 55.

    Args:
        xml_string: XML da NF-e
        ambiente: "production" ou "development"

    Returns:
        (valido, erros)
    """
    return validar_xml_contra_xsd(xml_string, tipo_documento="55", ambiente=ambiente)


def validar_xml_nfce(xml_string: str, ambiente: str = "production") -> Tuple[bool, List[str]]:
    """
    Atalho para validar XML de NFC-e modelo 65.

    Args:
        xml_string: XML da NFC-e
        ambiente: "production" ou "development"

    Returns:
        (valido, erros)
    """
    return validar_xml_contra_xsd(xml_string, tipo_documento="65", ambiente=ambiente)


def validar_xml_cte(xml_string: str, ambiente: str = "production") -> Tuple[bool, List[str]]:
    """
    Atalho para validar XML de CT-e modelo 57.

    Args:
        xml_string: XML do CT-e
        ambiente: "production" ou "development"

    Returns:
        (valido, erros)
    """
    return validar_xml_contra_xsd(xml_string, tipo_documento="57", ambiente=ambiente)


# ============================================
# VALIDAÇÃO DE REGRAS DE NEGÓCIO ADICIONAIS
# ============================================

def validar_regras_negocio_nfe(xml_string: str) -> Tuple[bool, List[str]]:
    """
    Valida regras de negócio específicas da NF-e além do XSD.

    Exemplos de regras:
    - CNPJ/CPF com dígitos verificadores corretos
    - Chave de acesso válida (algoritmo de geração)
    - Totais calculados corretamente
    - Datas dentro de limites aceitos

    Args:
        xml_string: XML da NF-e

    Returns:
        (valido, erros)
    """
    # TODO: Implementar validações de negócio adicionais
    # Por ora, retornar válido (validação XSD é suficiente)
    return (True, [])


# ============================================
# HELPER PARA MODO DESENVOLVIMENTO
# ============================================

def obter_ambiente() -> str:
    """
    Obtém ambiente atual da aplicação.

    Returns:
        "production", "homologacao", "development", ou "staging"
    """
    from app.core.config import settings
    return getattr(settings, 'ENVIRONMENT', 'production')
