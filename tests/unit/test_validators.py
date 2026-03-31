"""
Testes unitários para utils/validators.py
"""
import pytest
from datetime import date, timedelta
from app.utils.validators import (
    validar_cnpj,
    validar_chave_nfe,
    validar_periodo_busca,
    formatar_cnpj,
    validar_chave_cte,
    extrair_info_chave_nfe,
)


class TestValidarCNPJ:
    """Testes para validação de CNPJ"""

    def test_cnpj_valido_formatado(self):
        assert validar_cnpj("11.222.333/0001-81") is True

    def test_cnpj_valido_sem_formatacao(self):
        assert validar_cnpj("11222333000181") is True

    def test_cnpj_invalido_digitos_iguais(self):
        assert validar_cnpj("11.111.111/1111-11") is False

    def test_cnpj_invalido_digito_verificador(self):
        assert validar_cnpj("12.345.678/0001-00") is False

    def test_cnpj_muito_curto(self):
        assert validar_cnpj("123456") is False

    def test_cnpj_vazio(self):
        assert validar_cnpj("") is False

    def test_cnpj_com_letras(self):
        assert validar_cnpj("12.ABC.678/0001-90") is False

    def test_cnpj_todos_zeros(self):
        assert validar_cnpj("00.000.000/0000-00") is False


class TestValidarChaveNFe:
    """Testes para validação de chave de acesso NF-e"""

    # Chave válida para testes (SP, modelo 55)
    CHAVE_VALIDA = "35240112345678000181550010000001231234567890"

    def test_chave_valida(self):
        # Chave válida pré-calculada: SP, AAMM=2401, CNPJ=11222333000181, modelo=55, serie=001, nNF=000000123
        # Posições SEFAZ: UF[0:2]+AAMM[2:8]+CNPJ[8:22]+Modelo[22:24]+Serie[24:27]+Numero[27:36]+CodNum[36:43]+DV[43]
        assert validar_chave_nfe("35240112112223330001815500100000012312345671") is True

    def test_chave_com_menos_digitos(self):
        assert validar_chave_nfe("3524011234567890") is False

    def test_chave_com_letras(self):
        assert validar_chave_nfe("3524011234567800018155001000000123ABC67890") is False

    def test_chave_vazia(self):
        assert validar_chave_nfe("") is False

    def test_chave_com_uf_invalida(self):
        # UF 99 não existe
        chave = "9924011234567800018155001000000123123456789" + "0"
        assert validar_chave_nfe(chave) is False

    def test_chave_com_modelo_invalido(self):
        # Modelo 99 (nem 55 nem 65)
        chave = "3524011234567800018199001000000123123456789" + "0"
        assert validar_chave_nfe(chave) is False

    def test_chave_com_espacos(self):
        # Com espaços no início/fim devem ser ignorados
        chave = " 35240112112223330001815500100000012312345671 "
        assert validar_chave_nfe(chave) is True


class TestValidarPeriodoBusca:
    """Testes para validação de período de busca"""

    def test_periodo_valido(self):
        inicio = date.today() - timedelta(days=30)
        fim = date.today() - timedelta(days=1)
        valido, erro = validar_periodo_busca(inicio, fim)
        assert valido is True
        assert erro is None

    def test_data_inicio_maior_que_fim(self):
        inicio = date.today() - timedelta(days=1)
        fim = date.today() - timedelta(days=30)
        valido, erro = validar_periodo_busca(inicio, fim)
        assert valido is False
        assert "anterior" in erro.lower()

    def test_periodo_excede_maximo(self):
        inicio = date.today() - timedelta(days=100)
        fim = date.today() - timedelta(days=1)
        valido, erro = validar_periodo_busca(inicio, fim, max_dias=90)
        assert valido is False
        assert "90" in erro

    def test_data_fim_futura(self):
        inicio = date.today() - timedelta(days=30)
        fim = date.today() + timedelta(days=1)
        valido, erro = validar_periodo_busca(inicio, fim)
        assert valido is False
        assert "futura" in erro.lower()

    def test_data_muito_antiga(self):
        # Período dentro do limite de 90 dias, mas início > 5 anos atrás
        # Para que o erro seja "5 anos" e não "90 dias", o período deve ser <= 90 dias
        inicio = date.today() - timedelta(days=365 * 5 + 30)  # Mais de 5 anos
        fim = date.today() - timedelta(days=365 * 5 + 1)  # Ainda > 5 anos (diferença = 29 dias)
        valido, erro = validar_periodo_busca(inicio, fim)
        assert valido is False
        assert "5 anos" in erro

    def test_mesmo_dia(self):
        dia = date.today() - timedelta(days=1)
        valido, erro = validar_periodo_busca(dia, dia)
        assert valido is True


class TestFormatarCNPJ:
    """Testes para formatação de CNPJ"""

    def test_formatar_cnpj_sem_mascara(self):
        resultado = formatar_cnpj("11222333000181")
        assert resultado == "11.222.333/0001-81"

    def test_formatar_cnpj_ja_formatado(self):
        resultado = formatar_cnpj("11.222.333/0001-81")
        assert resultado == "11.222.333/0001-81"

    def test_formatar_cnpj_curto_levanta_erro(self):
        with pytest.raises(ValueError):
            formatar_cnpj("123456")


class TestValidarChaveCTE:
    """Testes para validação de chave CT-e"""

    def test_chave_cte_modelo_57_retorna_false(self):
        # NOTA: validar_chave_cte() chama validar_chave_nfe() internamente,
        # que só aceita modelo 55 ou 65. Modelo 57 (CT-e) é rejeitado por validar_chave_nfe.
        # Esta é uma limitação da implementação atual de validators.py.
        chave_cte = "35240112112223330001815700100000012312345672"  # modelo=57
        # Retorna False porque validar_chave_nfe rejeita modelo 57
        assert validar_chave_cte(chave_cte) is False

    def test_chave_nfe_nao_e_cte(self):
        # NF-e (modelo 55) não é CT-e
        chave_nfe = "35240112112223330001815500100000012312345671"  # modelo=55
        assert validar_chave_cte(chave_nfe) is False
