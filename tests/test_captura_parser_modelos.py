from app.services.captura_sefaz_service import CapturaService


def _svc() -> CapturaService:
    return CapturaService()


def test_montar_payload_nfe_modelo_55():
    svc = _svc()
    xml_nfe = """
    <nfeProc xmlns="http://www.portalfiscal.inf.br/nfe">
      <NFe>
        <infNFe Id="NFe35190201234567000190550010000012341000012345">
          <ide>
            <mod>55</mod>
            <serie>1</serie>
            <nNF>1234</nNF>
            <dhEmi>2026-02-20T10:00:00-03:00</dhEmi>
            <tpNF>1</tpNF>
          </ide>
          <emit>
            <CNPJ>01234567000190</CNPJ>
            <xNome>EMITENTE LTDA</xNome>
          </emit>
          <dest>
            <CNPJ>10987654000199</CNPJ>
            <xNome>DESTINATARIO SA</xNome>
          </dest>
          <total><ICMSTot><vNF>1500.55</vNF></ICMSTot></total>
          <protNFe><infProt><nProt>135260000000001</nProt><cStat>100</cStat></infProt></protNFe>
        </infNFe>
      </NFe>
    </nfeProc>
    """.strip()

    payload = svc._montar_payload_nota(  # noqa: SLF001
        {"xml": xml_nfe, "schema": "procNFe_v4.00", "nsu": 10},
        cnpj_empresa="01234567000190",
        empresa_id="empresa",
    )

    assert payload is not None
    assert payload["tipo_nf"] == "NFe"
    assert payload["modelo"] == "55"
    assert payload["numero_nf"] == "1234"
    assert payload["valor_total"] == 1500.55
    assert payload["cnpj_emitente"] == "01.234.567/0001-90"
    assert payload["cnpj_destinatario"] == "10.987.654/0001-99"
    assert payload["tipo_operacao"] == "saida"


def test_montar_payload_nfce_modelo_65_sem_confundir_emitente_destinatario():
    svc = _svc()
    xml_nfce = """
    <nfeProc xmlns="http://www.portalfiscal.inf.br/nfe">
      <NFe>
        <infNFe Id="NFe35190299887766000199650010000043211000098765">
          <ide>
            <mod>65</mod>
            <serie>1</serie>
            <nNF>4321</nNF>
            <dhEmi>2026-02-21T11:00:00-03:00</dhEmi>
            <tpNF>1</tpNF>
          </ide>
          <emit>
            <CNPJ>99887766000199</CNPJ>
            <xNome>MERCADO TESTE</xNome>
          </emit>
          <dest>
            <CPF>12345678901</CPF>
            <xNome>CONSUMIDOR FINAL</xNome>
          </dest>
          <total><ICMSTot><vNF>210.90</vNF></ICMSTot></total>
          <protNFe><infProt><nProt>135260000000002</nProt><cStat>100</cStat></infProt></protNFe>
        </infNFe>
      </NFe>
    </nfeProc>
    """.strip()

    payload = svc._montar_payload_nota(  # noqa: SLF001
        {"xml": xml_nfce, "schema": "procNFCe_v4.00", "nsu": 11},
        cnpj_empresa="99887766000199",
        empresa_id="empresa",
    )

    assert payload is not None
    assert payload["tipo_nf"] == "NFCe"
    assert payload["modelo"] == "65"
    assert payload["valor_total"] == 210.9
    assert payload["cnpj_emitente"] == "99.887.766/0001-99"
    # Destinatario CPF nao deve ser confundido como CNPJ do emitente.
    assert payload["cnpj_destinatario"] is None
    assert payload["tipo_operacao"] == "saida"


def test_montar_payload_cte_modelo_57():
    svc = _svc()
    xml_cte = """
    <cteProc xmlns="http://www.portalfiscal.inf.br/cte">
      <CTe>
        <infCte Id="CTe35190211222333000144570010000055561000055561">
          <ide>
            <mod>57</mod>
            <serie>1</serie>
            <nCT>5556</nCT>
            <dhEmi>2026-02-22T12:00:00-03:00</dhEmi>
          </ide>
          <emit>
            <CNPJ>11222333000144</CNPJ>
            <xNome>TRANSPORTADORA XPTO</xNome>
          </emit>
          <dest>
            <CNPJ>66778899000155</CNPJ>
            <xNome>DESTINO COMERCIO</xNome>
          </dest>
          <vPrest><vTPrest>987.65</vTPrest></vPrest>
          <protCTe><infProt><nProt>235260000000001</nProt><cStat>100</cStat></infProt></protCTe>
        </infCte>
      </CTe>
    </cteProc>
    """.strip()

    payload = svc._montar_payload_nota(  # noqa: SLF001
        {"xml": xml_cte, "schema": "procCTe_v4.00", "nsu": 12},
        cnpj_empresa="11222333000144",
        empresa_id="empresa",
    )

    assert payload is not None
    assert payload["tipo_nf"] == "CTe"
    assert payload["modelo"] == "57"
    assert payload["numero_nf"] == "5556"
    assert payload["valor_total"] == 987.65
    assert payload["cnpj_emitente"] == "11.222.333/0001-44"
    assert payload["cnpj_destinatario"] == "66.778.899/0001-55"
    assert payload["tipo_operacao"] == "saida"


def test_nao_gera_payload_para_evento():
    svc = _svc()
    xml_evento = """
    <procEventoNFe xmlns="http://www.portalfiscal.inf.br/nfe">
      <retEvento><infEvento><tpEvento>110111</tpEvento></infEvento></retEvento>
    </procEventoNFe>
    """.strip()

    payload = svc._montar_payload_nota(  # noqa: SLF001
        {"xml": xml_evento, "schema": "procEventoNFe_v1.00", "nsu": 20},
        cnpj_empresa="01234567000190",
        empresa_id="empresa",
    )

    assert payload is None


def test_inferir_modelo_por_schema_cteos_e_mdfe():
    svc = _svc()
    chave_cteos = "35190211222333000144670010000099991000099991"
    chave_mdfe = "35190211222333000144580010000011111000011111"

    modelo_cteos = svc._inferir_modelo_documento(  # noqa: SLF001
        xml_doc="<xml/>",
        schema="procCTeOS_v3.00",
        chave=chave_cteos,
    )
    modelo_mdfe = svc._inferir_modelo_documento(  # noqa: SLF001
        xml_doc="<xml/>",
        schema="procMDFe_v3.00",
        chave=chave_mdfe,
    )

    assert modelo_cteos == "67"
    assert modelo_mdfe == "58"
    assert svc._mapear_tipo_nf(modelo_cteos) == "CTe"  # noqa: SLF001
    assert svc._mapear_tipo_nf(modelo_mdfe) == "CTe"  # noqa: SLF001
