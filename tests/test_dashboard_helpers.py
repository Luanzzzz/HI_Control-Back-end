from app.api.v1.endpoints import dashboard_endpoints as de


def test_normalizar_tipo_param_mapeia_tipos_suportados():
    assert de._normalizar_tipo_param("NFe") == "NFe"  # noqa: SLF001
    assert de._normalizar_tipo_param("NF-e") == "NFe"  # noqa: SLF001
    assert de._normalizar_tipo_param("NFCe") == "NFCe"  # noqa: SLF001
    assert de._normalizar_tipo_param("CT-e") == "CTe"  # noqa: SLF001
    assert de._normalizar_tipo_param("NFSe") == "NFSe"  # noqa: SLF001
    assert de._normalizar_tipo_param("Todos") is None  # noqa: SLF001


def test_normalizar_status_param_mapeia_status_ui():
    assert de._normalizar_status_param("Ativa") == "autorizada"  # noqa: SLF001
    assert de._normalizar_status_param("Cancelada") == "cancelada"  # noqa: SLF001
    assert de._normalizar_status_param("Denegada") == "denegada"  # noqa: SLF001
    assert de._normalizar_status_param("Processando") == "processando"  # noqa: SLF001
    assert de._normalizar_status_param("Todos") is None  # noqa: SLF001


def test_normalizar_retencao_param():
    assert de._normalizar_retencao_param("Com retencao") == "com"  # noqa: SLF001
    assert de._normalizar_retencao_param("Sem retencao") == "sem"  # noqa: SLF001
    assert de._normalizar_retencao_param("Todas") == "todas"  # noqa: SLF001


def test_filtrar_por_retencao():
    rows = [
        {"id": 1, "valor_iss": 10, "valor_pis": 0, "valor_cofins": 0},
        {"id": 2, "valor_iss": 0, "valor_pis": 0, "valor_cofins": 0},
    ]
    com = de._filtrar_por_retencao(rows, "com")  # noqa: SLF001
    sem = de._filtrar_por_retencao(rows, "sem")  # noqa: SLF001
    assert [r["id"] for r in com] == [1]
    assert [r["id"] for r in sem] == [2]


def test_sanitizar_link_visualizacao_ignora_url_tecnica():
    url_tecnica = "https://www.w3.org/TR/xmlenc-core1/"
    assert de._sanitizar_link_visualizacao(url_tecnica) == ""  # noqa: SLF001


def test_sanitizar_link_visualizacao_aceita_url_fiscal():
    url_fiscal = "https://adn.nfse.gov.br/consultapublica?chave=123"
    assert de._sanitizar_link_visualizacao(url_fiscal) == url_fiscal  # noqa: SLF001


def test_obter_endpoints_danfse_oficial_respeita_ambiente(monkeypatch):
    monkeypatch.setenv("SEFAZ_AMBIENTE", "producao")
    monkeypatch.setenv("NFSE_DANFSE_URL_PRODUCAO", "https://prod.exemplo/danfse")
    monkeypatch.setenv("NFSE_DANFSE_URL_HOMOLOGACAO", "https://hml.exemplo/danfse")
    monkeypatch.setenv("NFSE_DANFSE_TENTAR_HOMOLOGACAO_FALLBACK", "true")

    endpoints = de._obter_endpoints_danfse_oficial()  # noqa: SLF001
    assert endpoints[0] == "https://prod.exemplo/danfse"
    assert "https://hml.exemplo/danfse" in endpoints


def test_obter_endpoints_danfse_oficial_homologacao_primeiro(monkeypatch):
    monkeypatch.setenv("SEFAZ_AMBIENTE", "homologacao")
    monkeypatch.setenv("NFSE_DANFSE_URL_PRODUCAO", "https://prod.exemplo/danfse")
    monkeypatch.setenv("NFSE_DANFSE_URL_HOMOLOGACAO", "https://hml.exemplo/danfse")
    monkeypatch.setenv("NFSE_DANFSE_TENTAR_HOMOLOGACAO_FALLBACK", "true")

    endpoints = de._obter_endpoints_danfse_oficial()  # noqa: SLF001
    assert endpoints[0] == "https://hml.exemplo/danfse"
    assert "https://prod.exemplo/danfse" in endpoints
