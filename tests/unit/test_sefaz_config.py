"""
Testes unitários para core/sefaz_config.py
"""
import pytest
from app.core.sefaz_config import (
    SEFAZ_ENDPOINTS_HOMOLOGACAO,
    UF_CODES,
    SEFAZ_STATUS_CODES,
    obter_endpoint_sefaz,
    obter_codigo_uf,
    validar_uf,
    obter_mensagem_sefaz,
    AMBIENTE_PADRAO,
    TIMEOUT_SEFAZ,
    RETRY_ATTEMPTS,
    CACHE_TTL_SECONDS,
)


class TestAmbienteConfig:
    """Testa configurações gerais"""

    def test_ambiente_padrao_homologacao(self):
        assert AMBIENTE_PADRAO == "homologacao"

    def test_timeout_positivo(self):
        assert TIMEOUT_SEFAZ > 0

    def test_retry_positivo(self):
        assert RETRY_ATTEMPTS > 0

    def test_cache_ttl_positivo(self):
        assert CACHE_TTL_SECONDS > 0


class TestUFCodes:
    """Testa mapeamento de UFs"""

    def test_todos_estados_presentes(self):
        estados_esperados = [
            "AC", "AL", "AM", "AP", "BA", "CE", "DF", "ES", "GO",
            "MA", "MG", "MS", "MT", "PA", "PB", "PE", "PI", "PR",
            "RJ", "RN", "RO", "RR", "RS", "SC", "SE", "SP", "TO"
        ]
        for uf in estados_esperados:
            assert uf in UF_CODES, f"UF {uf} não encontrada"

    def test_total_27_estados(self):
        assert len(UF_CODES) == 27

    def test_sp_codigo_35(self):
        assert UF_CODES["SP"] == "35"

    def test_rj_codigo_33(self):
        assert UF_CODES["RJ"] == "33"

    def test_mg_codigo_31(self):
        assert UF_CODES["MG"] == "31"


class TestEndpointsSefaz:
    """Testa endpoints SEFAZ configurados"""

    def test_todos_estados_tem_endpoints(self):
        for uf in UF_CODES.keys():
            assert uf in SEFAZ_ENDPOINTS_HOMOLOGACAO, f"UF {uf} sem endpoints"

    def test_cada_estado_tem_6_operacoes(self):
        operacoes_esperadas = {
            "autorizacao", "retorno_autorizacao", "consulta",
            "status_servico", "cancelamento", "inutilizacao"
        }
        for uf, endpoints in SEFAZ_ENDPOINTS_HOMOLOGACAO.items():
            assert set(endpoints.keys()) == operacoes_esperadas, \
                f"UF {uf} com operações inconsistentes: {set(endpoints.keys())}"

    def test_urls_iniciam_com_https(self):
        for uf, endpoints in SEFAZ_ENDPOINTS_HOMOLOGACAO.items():
            for operacao, url in endpoints.items():
                assert url.startswith("https://"), \
                    f"URL não HTTPS para {uf}/{operacao}: {url}"

    def test_sp_endpoints_especificos(self):
        sp = SEFAZ_ENDPOINTS_HOMOLOGACAO["SP"]
        assert "fazenda.sp.gov.br" in sp["autorizacao"]
        assert "fazenda.sp.gov.br" in sp["consulta"]

    def test_estados_svrs(self):
        estados_svrs = ["AC", "AL", "AP", "DF", "PB", "RJ", "RO", "RR", "SC", "SE", "TO"]
        for uf in estados_svrs:
            assert "svrs.rs.gov.br" in SEFAZ_ENDPOINTS_HOMOLOGACAO[uf]["autorizacao"], \
                f"Estado {uf} deveria usar SVRS"


class TestObterEndpointSefaz:
    """Testa função obter_endpoint_sefaz"""

    def test_endpoint_valido_sp(self):
        url = obter_endpoint_sefaz("SP", "autorizacao")
        assert url.startswith("https://")
        assert "fazenda.sp.gov.br" in url

    def test_endpoint_valido_mg_consulta(self):
        url = obter_endpoint_sefaz("MG", "consulta")
        assert url.startswith("https://")

    def test_uf_invalida_levanta_erro(self):
        with pytest.raises(ValueError, match="UF inválida"):
            obter_endpoint_sefaz("XX", "autorizacao")

    def test_operacao_invalida_levanta_erro(self):
        with pytest.raises(ValueError, match="Operação inválida"):
            obter_endpoint_sefaz("SP", "operacao_inexistente")


class TestObterCodigoUF:
    """Testa função obter_codigo_uf"""

    def test_codigo_sp(self):
        assert obter_codigo_uf("SP") == "35"

    def test_codigo_rj(self):
        assert obter_codigo_uf("RJ") == "33"

    def test_uf_invalida_levanta_erro(self):
        with pytest.raises(ValueError):
            obter_codigo_uf("XX")


class TestValidarUF:
    """Testa função validar_uf"""

    def test_uf_valida(self):
        assert validar_uf("SP") is True

    def test_uf_invalida(self):
        assert validar_uf("XX") is False

    def test_uf_minuscula_invalida(self):
        assert validar_uf("sp") is False


class TestStatusCodes:
    """Testa mapeamento de status SEFAZ"""

    def test_codigo_100_autorizado(self):
        mensagem = obter_mensagem_sefaz("100")
        assert "Autorizado" in mensagem

    def test_codigo_101_cancelamento(self):
        mensagem = obter_mensagem_sefaz("101")
        assert "Cancelamento" in mensagem

    def test_codigo_desconhecido(self):
        mensagem = obter_mensagem_sefaz("000")
        assert "000" in mensagem

    def test_codigo_999_erro(self):
        mensagem = obter_mensagem_sefaz("999")
        assert "999" in mensagem or "Erro" in mensagem

    def test_todos_codigos_sao_strings(self):
        for codigo, mensagem in SEFAZ_STATUS_CODES.items():
            assert isinstance(codigo, str)
            assert isinstance(mensagem, str)
