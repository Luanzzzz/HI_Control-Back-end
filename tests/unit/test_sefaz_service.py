"""
Testes unitários para services/sefaz_service.py
"""
import pytest
from datetime import datetime, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.sefaz_service import (
    SefazService,
    SefazException,
    SefazTimeoutError,
    SefazValidationError,
    SefazAuthorizationError,
)
from app.adapters.mock_sefaz_client import MOCK_XML_DISTRIBUICAO_SUCESSO
from app.models.nfe_busca import DistribuicaoResponseModel


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

    def test_obter_url_distribuicao_usa_ambiente_atual(self, service):
        service.ambiente = "producao"
        url = service._obter_url_distribuicao()
        assert url == "https://www1.nfe.fazenda.gov.br/NFeDistribuicaoDFe/NFeDistribuicaoDFe.asmx"

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
        mock_db.table.return_value.select.return_value.eq.return_value.in_.return_value.order.return_value\
            .range.return_value.execute.return_value = MagicMock(data=[], count=0)
        mock_db.table.return_value.select.return_value.eq.return_value.in_.return_value\
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
        mock_db.table.return_value.select.return_value.eq.return_value.in_.return_value.order.return_value\
            .range.return_value.execute.return_value = MagicMock(data=[nota_row])
        mock_db.table.return_value.select.return_value.eq.return_value.in_.return_value\
            .execute.return_value = MagicMock(data=[nota_row], count=1)

        with patch("app.db.supabase_client.supabase_admin", mock_db):
            resultado = service.buscar_notas_por_cnpj(
                cnpj="12345678000181",
                empresa_id="empresa-uuid",
            )
            assert resultado.status_codigo == "138"
            assert len(resultado.notas_encontradas) == 1

    def test_obter_maior_nsu_empresa_ignora_registros_nfse(self, service):
        mock_db = MagicMock()
        mock_db.table.return_value.select.return_value.eq.return_value.in_.return_value.gt.return_value.order.return_value\
            .limit.return_value.execute.return_value = MagicMock(data=[
                {"chave_acesso": "NFSEAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA", "nsu": 9999},
                {"chave_acesso": "35240112112223330001815500100000012312345671", "nsu": 120},
            ])

        with patch("app.db.supabase_client.supabase_admin", mock_db):
            resultado = service._obter_maior_nsu_empresa("empresa-uuid")

        assert resultado == 120

    def test_parsear_resposta_distribuicao_mock(self, service):
        resultado = service._parsear_resposta_distribuicao(MOCK_XML_DISTRIBUICAO_SUCESSO)
        assert resultado.status_codigo == "138"
        assert resultado.total_notas == 3
        assert resultado.notas_encontradas[0].nsu == 123456

    @pytest.mark.asyncio
    async def test_sincronizar_e_buscar_notas_primeira_pagina(self, service):
        resposta_local = DistribuicaoResponseModel(
            status_codigo="138",
            motivo="Encontradas 2 notas no banco",
            notas_encontradas=[],
            ultimo_nsu=2,
            max_nsu=2,
            total_notas=2,
        )

        with patch.object(
            service,
            "_sincronizar_notas_novas",
            AsyncMock(return_value={
                "fonte": "sefaz",
                "sincronizacao_realizada": True,
                "certificado_usado": "empresa",
                "novas_notas_sincronizadas": 2,
                "mensagem_sincronizacao": "Documento localizado",
                "status_codigo_sincronizacao": "138",
                "ultimo_nsu_sincronizacao": 10,
                "max_nsu_sincronizacao": 10,
            }),
        ) as sync_mock, patch.object(
            service,
            "buscar_notas_por_cnpj",
            return_value=resposta_local,
        ) as busca_local_mock:
            resultado = await service.sincronizar_e_buscar_notas_por_cnpj(
                cnpj="12345678000181",
                empresa_id="empresa-uuid",
                contador_id="usuario-uuid",
                nsu_inicial=None,
            )

        sync_mock.assert_awaited_once()
        busca_local_mock.assert_called_once()
        assert resultado["fonte"] == "sefaz"
        assert resultado["sincronizacao_realizada"] is True
        assert resultado["response"].status_codigo == "138"

    @pytest.mark.asyncio
    async def test_sincronizar_e_buscar_notas_paginacao_nao_reconsulta_sefaz(self, service):
        resposta_local = DistribuicaoResponseModel(
            status_codigo="138",
            motivo="Encontradas 2 notas no banco",
            notas_encontradas=[],
            ultimo_nsu=4,
            max_nsu=8,
            total_notas=2,
        )

        with patch.object(
            service,
            "_sincronizar_notas_novas",
            AsyncMock(),
        ) as sync_mock, patch.object(
            service,
            "buscar_notas_por_cnpj",
            return_value=resposta_local,
        ) as busca_local_mock:
            resultado = await service.sincronizar_e_buscar_notas_por_cnpj(
                cnpj="12345678000181",
                empresa_id="empresa-uuid",
                contador_id="usuario-uuid",
                nsu_inicial=50,
            )

        sync_mock.assert_not_awaited()
        busca_local_mock.assert_called_once()
        assert resultado["fonte"] == "banco_local"
        assert resultado["response"].ultimo_nsu == 4

    @pytest.mark.asyncio
    async def test_sincronizar_notas_novas_tenta_producao_apos_homologacao_vazia(self, service):
        service.ambiente = "homologacao"
        retorno_homologacao = DistribuicaoResponseModel(
            status_codigo="137",
            motivo="Nenhum documento localizado",
            notas_encontradas=[],
            ultimo_nsu=0,
            max_nsu=0,
            total_notas=0,
        )
        retorno_producao = DistribuicaoResponseModel(
            status_codigo="138",
            motivo="Documento localizado",
            notas_encontradas=[],
            ultimo_nsu=10,
            max_nsu=10,
            total_notas=0,
        )

        with patch.object(service, "_obter_uf_empresa", return_value="MG"), patch.object(
            service,
            "_obter_maior_nsu_empresa",
            return_value=0,
        ), patch.object(
            service,
            "_registrar_log_distribuicao",
        ), patch(
            "app.adapters.mock_sefaz_client.get_distribuicao_client",
            return_value=None,
        ), patch(
            "app.services.certificado_service.certificado_service.obter_certificado_para_busca",
            AsyncMock(return_value=(b"cert", "senha", "empresa")),
        ), patch.object(
            service,
            "_enviar_distribuicao_dfe",
            side_effect=["<xml-homologacao />", "<xml-producao />"],
        ) as enviar_mock, patch.object(
            service,
            "_parsear_resposta_distribuicao",
            side_effect=[retorno_homologacao, retorno_producao],
        ):
            resultado = await service._sincronizar_notas_novas(
                cnpj="12345678000181",
                empresa_id="empresa-uuid",
                contador_id="contador-uuid",
            )

        assert enviar_mock.call_count == 2
        assert enviar_mock.call_args_list[0].args[0] == service._obter_url_distribuicao("homologacao")
        assert enviar_mock.call_args_list[1].args[0] == service._obter_url_distribuicao("producao")
        assert resultado["sincronizacao_realizada"] is True
        assert resultado["status_codigo_sincronizacao"] == "138"
        assert resultado["ambiente_consulta"] == "producao"

    @pytest.mark.asyncio
    async def test_sincronizar_notas_novas_reprocessa_nsu_quando_sefaz_retorna_589(self, service):
        service.ambiente = "producao"
        retorno_nsu_invalido = DistribuicaoResponseModel(
            status_codigo="589",
            motivo="NSU maior que o permitido",
            notas_encontradas=[],
            ultimo_nsu=0,
            max_nsu=0,
            total_notas=0,
        )
        retorno_reprocessado = DistribuicaoResponseModel(
            status_codigo="138",
            motivo="Documento localizado",
            notas_encontradas=[],
            ultimo_nsu=7,
            max_nsu=7,
            total_notas=0,
        )

        with patch.object(service, "_obter_uf_empresa", return_value="MG"), patch.object(
            service,
            "_obter_maior_nsu_empresa",
            return_value=9999,
        ), patch.object(
            service,
            "_registrar_log_distribuicao",
        ), patch(
            "app.adapters.mock_sefaz_client.get_distribuicao_client",
            return_value=None,
        ), patch(
            "app.services.certificado_service.certificado_service.obter_certificado_para_busca",
            AsyncMock(return_value=(b"cert", "senha", "empresa")),
        ), patch.object(
            service,
            "_enviar_distribuicao_dfe",
            side_effect=["<xml-589 />", "<xml-0 />"],
        ) as enviar_mock, patch.object(
            service,
            "_parsear_resposta_distribuicao",
            side_effect=[retorno_nsu_invalido, retorno_reprocessado],
        ):
            resultado = await service._sincronizar_notas_novas(
                cnpj="12345678000181",
                empresa_id="empresa-uuid",
                contador_id="contador-uuid",
            )

        assert enviar_mock.call_count == 2
        primeiro_payload = enviar_mock.call_args_list[0].args[1]
        segundo_payload = enviar_mock.call_args_list[1].args[1]
        assert "<ultNSU>000000000009999</ultNSU>" in primeiro_payload
        assert "<ultNSU>000000000000000</ultNSU>" in segundo_payload
        assert resultado["status_codigo_sincronizacao"] == "138"


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

    def test_construir_xml_consulta_respeita_ambiente_atual(self, service):
        service.ambiente = "producao"
        xml = service._construir_xml_consulta("35240112112223330001815500100000012312345671")
        assert "<tpAmb>1</tpAmb>" in xml

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

    def test_construir_envelope_soap_distribuicao_sem_cdata(self, service):
        xml = service._construir_envelope_soap_distribuicao(
            service._construir_xml_distribuicao(
                cnpj="12345678000181",
                empresa_uf="SP",
                ult_nsu=0,
            )
        )
        assert "soap:Envelope" in xml
        assert "nfeDistDFeInteresse" in xml
        assert "nfeDadosMsg" in xml
        assert "CDATA" not in xml
