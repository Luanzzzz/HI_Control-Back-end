"""
Validadores de dados fiscais brasileiros
"""
from datetime import date, datetime, timedelta
import re
from typing import Iterable, Optional


def calcular_digito_verificador_chave(chave_sem_dv: str) -> str:
    """
    Calcula o dígito verificador da chave fiscal usando módulo 11.

    Args:
        chave_sem_dv: Primeiros 43 dígitos da chave

    Returns:
        Dígito verificador calculado como string
    """
    if not isinstance(chave_sem_dv, str):
        raise ValueError("Chave deve ser uma string")

    chave = chave_sem_dv.strip().replace(" ", "")
    if not chave.isdigit() or len(chave) != 43:
        raise ValueError("Chave sem DV deve conter exatamente 43 dígitos numéricos")

    pesos = [4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    soma = sum(int(chave[idx]) * pesos[idx] for idx in range(43))
    resto = soma % 11
    dv = 0 if resto in [0, 1] else 11 - resto
    return str(dv)


def _validar_chave_fiscal(chave: str, modelos_validos: Iterable[str]) -> bool:
    """
    Valida estrutura e dígito verificador de uma chave fiscal.

    Args:
        chave: Chave de acesso completa com 44 dígitos
        modelos_validos: Modelos aceitos para a validação

    Returns:
        True se a chave for válida
    """
    if not isinstance(chave, str):
        return False

    chave = chave.strip().replace(' ', '')

    if not chave.isdigit() or len(chave) != 44:
        return False

    uf = chave[0:2]
    modelo = chave[22:24]

    ufs_validas = [
        '11', '12', '13', '14', '15', '16', '17',
        '21', '22', '23', '24', '25', '26', '27', '28', '29',
        '31', '32', '33', '35',
        '41', '42', '43',
        '50', '51', '52', '53'
    ]
    if uf not in ufs_validas:
        return False

    if modelo not in set(modelos_validos):
        return False

    dv_calculado = calcular_digito_verificador_chave(chave[:43])
    return chave[43] == dv_calculado


def validar_cnpj(cnpj: str) -> bool:
    """
    Valida CNPJ brasileiro com dígitos verificadores

    Args:
        cnpj: CNPJ formatado (00.000.000/0000-00) ou apenas dígitos

    Returns:
        True se CNPJ válido, False caso contrário
    """
    if not isinstance(cnpj, str):
        return False

    # Remover formatação
    cnpj_digits = re.sub(r'[^\d]', '', cnpj)

    # Verificar se tem 14 dígitos
    if len(cnpj_digits) != 14:
        return False

    # Verificar se todos os dígitos são iguais
    if cnpj_digits == cnpj_digits[0] * 14:
        return False

    # Calcular primeiro dígito verificador
    soma = 0
    peso = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]

    for i in range(12):
        soma += int(cnpj_digits[i]) * peso[i]

    resto = soma % 11
    digito1 = 0 if resto < 2 else 11 - resto

    if int(cnpj_digits[12]) != digito1:
        return False

    # Calcular segundo dígito verificador
    soma = 0
    peso = [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]

    for i in range(13):
        soma += int(cnpj_digits[i]) * peso[i]

    resto = soma % 11
    digito2 = 0 if resto < 2 else 11 - resto

    if int(cnpj_digits[13]) != digito2:
        return False

    return True


def validar_chave_nfe(chave: str) -> bool:
    """
    Valida chave de acesso da NF-e (44 dígitos com DV)

    Estrutura da chave (44 dígitos):
    - Posições 1-2: UF (código IBGE)
    - Posições 3-8: AAMM (ano e mês de emissão)
    - Posições 9-22: CNPJ do emitente
    - Posições 23-24: Modelo (55 para NF-e, 65 para NFC-e)
    - Posições 25-27: Série
    - Posições 28-36: Número da NF
    - Posições 37-44: Código numérico + DV

    Args:
        chave: Chave de acesso (apenas números)

    Returns:
        True se chave válida, False caso contrário
    """
    return _validar_chave_fiscal(chave, modelos_validos=("55", "65"))


def validar_periodo_busca(data_inicio: date, data_fim: date, max_dias: int = 90) -> tuple[bool, Optional[str]]:
    """
    Valida período de busca de notas fiscais

    Args:
        data_inicio: Data inicial da busca
        data_fim: Data final da busca
        max_dias: Número máximo de dias permitido no período (padrão 90)

    Returns:
        Tupla (válido: bool, mensagem_erro: Optional[str])
    """
    # Verificar se data_inicio é anterior ou igual a data_fim
    if data_inicio > data_fim:
        return False, "Data inicial deve ser anterior ou igual à data final"

    # Verificar se período não excede máximo de dias
    diferenca = (data_fim - data_inicio).days

    if diferenca > max_dias:
        return False, f"Período de busca não pode exceder {max_dias} dias (período atual: {diferenca} dias)"

    # Verificar se data_fim não está no futuro
    hoje = date.today()
    if data_fim > hoje:
        return False, "Data final não pode ser futura"

    # Verificar se período não é muito antigo (opcional - 5 anos)
    cinco_anos_atras = hoje - timedelta(days=365 * 5)
    if data_inicio < cinco_anos_atras:
        return False, "Data inicial não pode ser superior a 5 anos no passado"

    return True, None


def formatar_cnpj(cnpj: str) -> str:
    """
    Formata CNPJ para padrão XX.XXX.XXX/XXXX-XX

    Args:
        cnpj: CNPJ com ou sem formatação

    Returns:
        CNPJ formatado
    """
    cnpj_digits = re.sub(r'[^\d]', '', cnpj)

    if len(cnpj_digits) != 14:
        raise ValueError("CNPJ deve ter 14 dígitos")

    return f"{cnpj_digits[0:2]}.{cnpj_digits[2:5]}.{cnpj_digits[5:8]}/{cnpj_digits[8:12]}-{cnpj_digits[12:14]}"


def validar_chave_cte(chave: str) -> bool:
    """
    Valida chave de acesso do CT-e (mesmo algoritmo da NF-e, modelo 57)

    Args:
        chave: Chave de acesso (44 dígitos)

    Returns:
        True se chave válida, False caso contrário
    """
    return _validar_chave_fiscal(chave, modelos_validos=("57",))


def extrair_info_chave_nfe(chave: str) -> dict:
    """
    Extrai informações da chave de acesso da NF-e

    Args:
        chave: Chave de acesso válida

    Returns:
        Dicionário com informações extraídas
    """
    if not validar_chave_nfe(chave):
        raise ValueError("Chave de acesso inválida")

    return {
        "uf": chave[0:2],
        "ano": f"20{chave[2:4]}",
        "mes": chave[4:6],
        "cnpj_emitente": formatar_cnpj(chave[8:22]),
        "modelo": chave[22:24],
        "serie": chave[24:27].lstrip('0') or '0',
        "numero": chave[27:36].lstrip('0') or '0',
        "codigo_numerico": chave[36:43],
        "dv": chave[43]
    }
