"""
Testes unitários para services/sefaz_service.py
"""
import pytest
from datetime import datetime, timedelta
from decimal import Decimal
from unittest.mock import MagicMock, patch

from app.services.sefaz_service import (
    SefazService,
    SefazException,
    SefazTimeoutError,
    SefazValidationError,
    SefazAuthorizationError,
)


class TestSefazException:
    """Testa as exceções customizadas"""

    def test_sefaz_exception_atributos(self):
        exc = SefazException("100", "Autorizado", "campo")
        assert exc.codigo == "100"
        assert exc.mensagem == "Autorizado"
        assert exc.campo_erro == "campo"

    def test_sefaz_exception_str(self):
        exc = SefazException("999", "Erro")
        assert "999" in str(exc)
        assert "Erro" in str(exc)

    def test_timeout_herda_de_sefaz_exception(self):
        exc = SefazTimeoutError("999", "Timeout")
        assert isinstance(exc, SefazException)

    def test_validation_herda_de_sefaz_exception(self):
        exc = SefazValidationError("204", "Inválido")
        assert isinstance(exc, SefazException)

    def test_auth_herda_de_sefaz_exception(self):
        exc = SefazAuthorizationError("539", "Auth error")
        assert isinstance(exc, SefazException)


class TestSefazServiceCache:
    """Testa o sistema de cache do SefazService"""

    @pytest.fixture
    def service(self):
        # Criar instância fresh para testes de cache
        from app.core.sefaz_config import _query_cache
        _query_cache.clear()
        return SefazService()

    def test_cache_inicialmente_vazio(self, service):
        resultado = service._get_cache("chave_inexistente")
        assert resultado is None

    def test_set_e_get_cache(self, service):
        from app.models.nfe_completa import SefazResponseModel
        response = SefazResponseModel(
            status_codigo="100",
            status_descricao="Autorizado",
            rejeicoes=[],
        )
        service._set_cache("chave_teste", response)
        cached = service._get_cache("chave_teste")
        assert cached is not None
        assert cached.status_codigo == "100"

    def test_invalidar_cache(self, service):
        from app.models.nfe_completa import SefazResponseModel
        response = SefazResponseModel(
            status_codigo="100",
            status_descricao="Autorizado",
            rejeicoes=[],
        )
        service._set_cache("chave_teste", response)
        service._invalidate_cache("chave_teste")
        assert service._get_cache("chave_teste") is None

    def test_cache_expirado_retorna_none(self, service):
        from app.models.nfe_completa import SefazResponseModel
        import time
        response = SefazResponseModel(
            status_codigo="100",
            status_descricao="Autorizado",
            rejeicoes=[],
        )
        # Inserir diretamente com timestamp expirado
        old_time = datetime.now() - timedelta(seconds=400)  # TTL é 300s
        service._cache["chave_expirada"] = (response, old_time)
        resultado = service._get_cache("chave_expirada")
        assert resultado is None


class TestSefazServiceValidacoes:
    """Testa validações do SefazService"""

    @pytest.fixture
    def service(self):
        return SefazService()

    def test_validar_cancelamento_apos_24h(self, service):
        data_antiga = datetime.now() - timedelta(hours=25)
        with pytest.raises(SefazValidationError, match="24 horas"):
            service._validar_cancelamento(data_antiga, "Motivo com mais de quinze chars")

    def test_validar_cancelamento_motivo_curto(self, service):
        data_recente = datetime.now() - timedelta(hours=1)
        with pytest.raises(SefazValidationError, match="15 caracteres"):
            service._validar_cancelamento(data_recente, "Curto")

    def test_validar_cancelamento_valido(self, service):
        data_recente = datetime.now() - timedelta(hours=1)
        # Não deve levantar exceção
        service._validar_cancelamento(data_recente, "Motivo com mais de quinze caracteres")

    def test_obter_url_sefaz_sp_consulta(self, service):
        url = service._obter_url_sefaz("SP", "consulta")
        assert url.startswith("https://")

    def test_obter_url_sefaz_uf_invalida(self, service):
        with pytest.raises(SefazException):
            service._obter_url_sefaz("XX", "consulta")

    def test_obter_url_sefaz_operacao_invalida(self, service):
        with pytest.raises(SefazException):
            service._obter_url_sefaz("SP", "operacao_nao_existe")

    def test_obter_codigo_uf_sp(self, service):
        assert service._obter_codigo_uf("SP") == "35"

    def test_obter_codigo_uf_invalida(self, service):
        assert service._obter_codigo_uf("XX") == "00"


class TestSefazServiceBuscarNotas:
    """Testa busca de notas no banco via SefazService"""

    @pytest.fixture
    def service(self):
        return SefazService()

    def test_buscar_notas_banco_vazio(self, service):
        mock_db = MagicMock()
        mock_db.table.return_value.select.return_value.eq.return_value.order.return_value\
            .range.return_value.execute.return_value = MagicMock(data=[], count=0)
        mock_db.table.return_value.select.return_value.eq.return_value\
            .execute.return_value = MagicMock(data=[], count=0)

        with patch("app.db.supabase_client.supabase_admin", mock_db):
            resultado = service.buscar_notas_por_cnpj(
                cnpj="12345678000181",
                empresa_id="empresa-uuid",
            )
            assert resultado.total_notas == 0
            assert resultado.status_codigo == "137"

    def test_buscar_notas_com_resultado(self, service):
        nota_row = {
            "chave_acesso": "35240112112223330001815500100000012312345671",
            "nsu": 100,
            "data_emissao": "2024-01-15T10:30:00",
            "tipo_operacao": "saida",
            "valor_total": "1000.00",
            "cnpj_emitente": "12345678000181",
            "nome_emitente": "Empresa Teste",
            "cnpj_destinatario": None,
            "cpf_destinatario": None,
            "nome_destinatario": None,
            "situacao": "autorizada",
            "protocolo": "135240000000001",
            "xml_resumo": None,
            "xml_completo": None,
        }
        mock_db = MagicMock()
        mock_db.table.return_value.select.return_value.eq.return_value.order.return_value\
            .range.return_value.execute.return_value = MagicMock(data=[nota_row])
        mock_db.table.return_value.select.return_value.eq.return_value\
            .execute.return_value = MagicMock(data=[nota_row], count=1)

        with patch("app.db.supabase_client.supabase_admin", mock_db):
            resultado = service.buscar_notas_por_cnpj(
                cnpj="12345678000181",
                empresa_id="empresa-uuid",
            )
            assert resultado.status_codigo == "138"
            assert len(resultado.notas_encontradas) == 1


class TestSefazServiceConstruirXML:
    """Testa construção de XMLs SEFAZ"""

    @pytest.fixture
    def service(self):
        return SefazService()

    def test_construir_xml_consulta(self, service):
        xml = service._construir_xml_consulta("35240112112223330001815500100000012312345671")
        assert "consSitNFe" in xml
        assert "CONSULTAR" in xml
        assert "35240112112223330001815500100000012312345671" in xml

    def test_construir_xml_consulta_tem_tipo_amb(self, service):
        xml = service._construir_xml_consulta("35240112112223330001815500100000012312345671")
        assert "<tpAmb>" in xml
        # Homologação = 2
        assert "<tpAmb>2</tpAmb>" in xml

    def test_construir_xml_cancelamento(self, service):
        xml = service._construir_xml_cancelamento(
            chave_acesso="35240112112223330001815500100000012312345671",
            protocolo="135240000000001",
            motivo="Cancelamento para teste com motivo adequado",
            cnpj="12345678000181",
        )
        assert "envEvento" in xml
        assert "110111" in xml  # Código de cancelamento
        assert "Cancelamento" in xml

    def test_construir_xml_inutilizacao(self, service):
        xml = service._construir_xml_inutilizacao(
            cnpj="12345678000181",
            uf="SP",
            serie="1",
            numero_inicial=1,
            numero_final=10,
            ano=24,
            motivo="Inutilizacao para teste com motivo valido",
        )
        assert "inutNFe" in xml
        assert "INUTILIZAR" in xml
        assert "12345678000181" in xml
