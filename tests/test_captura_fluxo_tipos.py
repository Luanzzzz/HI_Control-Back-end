from app.services.captura_sefaz_service import CapturaService


def _svc() -> CapturaService:
    return CapturaService()


def test_normalizar_tipos_habilitados_default_quando_lista_vazia():
    svc = _svc()
    assert svc._normalizar_tipos_habilitados([]) == ["NFSE", "NFE", "NFCE", "CTE"]  # noqa: SLF001


def test_normalizar_tipos_habilitados_remove_duplicados_e_invalidos():
    svc = _svc()
    tipos = svc._normalizar_tipos_habilitados(["NFE", "NFSE", "NFE", "foo", "CTE"])  # noqa: SLF001
    assert tipos == ["NFE", "NFSE", "CTE"]


def test_filtrar_payload_por_tipos_preserva_apenas_permitidos():
    svc = _svc()
    payload = [
        {"tipo_nf": "NFe", "id": 1},
        {"tipo_nf": "NFCe", "id": 2},
        {"tipo_nf": "CTe", "id": 3},
        {"tipo_nf": "NFSe", "id": 4},
    ]
    filtrado = svc._filtrar_payload_por_tipos(payload, ["NFE", "CTE"])  # noqa: SLF001
    assert [item["id"] for item in filtrado] == [1, 3]


def test_mapear_tipo_nf_para_modelos_suportados():
    svc = _svc()
    assert svc._mapear_tipo_nf("55") == "NFe"  # noqa: SLF001
    assert svc._mapear_tipo_nf("65") == "NFCe"  # noqa: SLF001
    assert svc._mapear_tipo_nf("57") == "CTe"  # noqa: SLF001
    assert svc._mapear_tipo_nf("67") == "CTe"  # noqa: SLF001
    assert svc._mapear_tipo_nf("58") == "CTe"  # noqa: SLF001
