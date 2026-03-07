"""
Testes unitários para services/real_consulta_service.py
"""
import pytest
from decimal import Decimal
from datetime import datetime
from unittest.mock import MagicMock, AsyncMock, patch

from app.services.real_consulta_service import RealConsultaService


CHAVE_TESTE = "35240112112223330001815500100000012312345671"

# XML de NF-e mínimo para testes
XML_NFE_VALIDO = b"""<?xml version="1.0" encoding="UTF-8"?>
<nfeProc xmlns="http://www.portalfiscal.inf.br/nfe">
  <NFe>
    <infNFe Id="NFe35240112112223330001815500100000012312345671" versao="4.00">
      <ide>
        <cUF>35</cUF>
        <nNF>123</nNF>
        <serie>1</serie>
        <mod>55</mod>
        <dhEmi>2024-01-15T10:30:00-03:00</dhEmi>
        <tpNF>1</tpNF>
      </ide>
      <emit>
        <CNPJ>11222333000181</CNPJ>
        <xNome>Empresa Teste LTDA</xNome>
        <IE>123456789</IE>
      </emit>
      <dest>
        <CNPJ>98765432000199</CNPJ>
        <xNome>Destinatario Teste</xNome>
      </dest>
      <total>
        <ICMSTot>
          <vNF>1000.00</vNF>
          <vProd>1000.00</vProd>
          <vICMS>180.00</vICMS>
          <vIPI>0.00</vIPI>
          <vPIS>16.50</vPIS>
          <vCOFINS>76.00</vCOFINS>
          <vFrete>0.00</vFrete>
          <vDesc>0.00</vDesc>
        </ICMSTot>
      </total>
    </infNFe>
  </NFe>
  <protNFe>
    <infProt>
      <nProt>135240000000001</nProt>
      <cStat>100</cStat>
    </infProt>
  </protNFe>
</nfeProc>"""

XML_NFE_INVALIDO = b"<xml_invalido/>"
XML_NFE_SEM_INF_NFE = b"""<?xml version="1.0" encoding="UTF-8"?>
<nfeProc xmlns="http://www.portalfiscal.inf.br/nfe">
  <NFe><dados>sem infNFe</dados></NFe>
</nfeProc>"""


class TestRealConsultaServiceImportarXML:
    """Testa importação de XML"""

    @pytest.fixture
    def service(self):
        return RealConsultaService()

    def test_importar_xml_valido(self, service):
        nota, metadados = service.importar_xml(XML_NFE_VALIDO, "empresa-uuid-123")
        assert nota.empresa_id == "empresa-uuid-123"
        assert nota.valor_total == Decimal("1000.00")
        assert nota.cnpj_emitente is not None

    def test_importar_xml_chave_extraida(self, service):
        nota, metadados = service.importar_xml(XML_NFE_VALIDO, "empresa-uuid-123")
        assert len(nota.chave_acesso) == 44

    def test_importar_xml_numero_nota(self, service):
        nota, metadados = service.importar_xml(XML_NFE_VALIDO, "empresa-uuid-123")
        assert nota.numero_nf == "123"

    def test_importar_xml_situacao_autorizada(self, service):
        nota, metadados = service.importar_xml(XML_NFE_VALIDO, "empresa-uuid-123")
        assert nota.situacao == "autorizada"

    def test_importar_xml_invalido_levanta_erro(self, service):
        with pytest.raises(ValueError, match="XML invalido"):
            service.importar_xml(b"<nao_eh_xml", "empresa-uuid-123")

    def test_importar_xml_sem_inf_nfe_levanta_erro(self, service):
        with pytest.raises(ValueError, match="infNFe"):
            service.importar_xml(XML_NFE_SEM_INF_NFE, "empresa-uuid-123")

    def test_importar_xml_metadados_contém_xml_completo(self, service):
        nota, metadados = service.importar_xml(XML_NFE_VALIDO, "empresa-uuid-123")
        assert "xml_completo" in metadados
        assert len(metadados["xml_completo"]) > 0

    def test_importar_xml_metadados_data_importacao(self, service):
        nota, metadados = service.importar_xml(XML_NFE_VALIDO, "empresa-uuid-123")
        assert "data_importacao" in metadados

    def test_importar_cte_levanta_not_implemented(self, service):
        xml_cte = b"""<?xml version="1.0"?>
<cteProc xmlns="http://www.portalfiscal.inf.br/cte">
  <CTe><infCte Id="CTe123"></infCte></CTe>
</cteProc>"""
        with pytest.raises(ValueError):
            service.importar_xml(xml_cte, "empresa-uuid-123")


class TestRealConsultaServiceValidacoes:
    """Testa métodos de validação do service"""

    @pytest.fixture
    def service(self):
        return RealConsultaService()

    def test_validar_chave_acesso_valida(self, service):
        assert service._validar_chave_acesso(CHAVE_TESTE) is True

    def test_validar_chave_acesso_curta(self, service):
        assert service._validar_chave_acesso("12345") is False

    def test_validar_chave_acesso_vazia(self, service):
        assert service._validar_chave_acesso("") is False

    def test_validar_chave_acesso_com_letras(self, service):
        assert service._validar_chave_acesso("A" * 44) is False

    def test_extrair_uf_sp(self, service):
        assert service._extrair_uf_da_chave(CHAVE_TESTE) == "SP"

    def test_extrair_uf_rj(self, service):
        chave_rj = "33" + CHAVE_TESTE[2:]
        assert service._extrair_uf_da_chave(chave_rj) == "RJ"

    def test_extrair_uf_codigo_desconhecido(self, service):
        chave_desconhecida = "99" + CHAVE_TESTE[2:]
        # Deve retornar fallback (SP)
        resultado = service._extrair_uf_da_chave(chave_desconhecida)
        assert resultado == "SP"


class TestRealConsultaServiceParseDatas:
    """Testa parsing de datas"""

    @pytest.fixture
    def service(self):
        return RealConsultaService()

    def test_parse_data_iso(self, service):
        resultado = service._parse_data("2024-01-15T10:30:00")
        assert resultado.year == 2024
        assert resultado.month == 1
        assert resultado.day == 15

    def test_parse_data_com_timezone(self, service):
        resultado = service._parse_data("2024-01-15T10:30:00-03:00")
        assert resultado.year == 2024

    def test_parse_data_vazia_retorna_now(self, service):
        resultado = service._parse_data("")
        assert isinstance(resultado, datetime)

    def test_parse_data_invalida_retorna_now(self, service):
        resultado = service._parse_data("data_invalida")
        assert isinstance(resultado, datetime)
