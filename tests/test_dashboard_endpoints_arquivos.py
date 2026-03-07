from __future__ import annotations

import pytest
from fastapi import HTTPException

from app.api.v1.endpoints import dashboard_endpoints as de


async def _read_stream(response) -> bytes:
    chunks = []
    async for chunk in response.body_iterator:
        chunks.append(chunk)
    return b"".join(chunks)


@pytest.mark.asyncio
async def test_baixar_xml_nota_empresa_retorna_xml(fake_db_factory, monkeypatch):
    async def _validar(*_args, **_kwargs):
        return {"id": "empresa-1"}

    monkeypatch.setattr(de, "_validar_empresa_usuario", _validar)

    db = fake_db_factory(
        {
            "notas_fiscais": [
                {
                    "id": "nota-1",
                    "empresa_id": "empresa-1",
                    "tipo_nf": "NFSe",
                    "numero_nf": "23",
                    "chave_acesso": "NFSExpto",
                    "xml_completo": "<nfse>ok</nfse>",
                    "xml_resumo": None,
                }
            ]
        }
    )

    response = await de.baixar_xml_nota_empresa(
        empresa_id="empresa-1",
        nota_id="nota-1",
        usuario={"id": "user-1"},
        db=db,
    )

    content = await _read_stream(response)
    assert response.media_type == "application/xml"
    assert b"<nfse>ok</nfse>" == content
    assert ".xml" in response.headers.get("Content-Disposition", "")


@pytest.mark.asyncio
async def test_baixar_xml_nota_empresa_sem_xml_retorna_404(fake_db_factory, monkeypatch):
    async def _validar(*_args, **_kwargs):
        return {"id": "empresa-1"}

    monkeypatch.setattr(de, "_validar_empresa_usuario", _validar)
    db = fake_db_factory(
        {
            "notas_fiscais": [
                {"id": "nota-1", "empresa_id": "empresa-1", "xml_completo": "", "xml_resumo": ""}
            ]
        }
    )

    with pytest.raises(HTTPException) as exc:
        await de.baixar_xml_nota_empresa(
            empresa_id="empresa-1",
            nota_id="nota-1",
            usuario={"id": "user-1"},
            db=db,
        )

    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_baixar_pdf_nota_empresa_prioriza_pdf_oficial(fake_db_factory, monkeypatch):
    async def _validar(*_args, **_kwargs):
        return {"id": "empresa-1"}

    async def _pdf_oficial(*_args, **_kwargs):
        return b"%PDF-1.4 official"

    monkeypatch.setattr(de, "_validar_empresa_usuario", _validar)
    monkeypatch.setattr(de, "_obter_pdf_oficial_nota", _pdf_oficial)

    db = fake_db_factory(
        {
            "notas_fiscais": [
                {
                    "id": "nota-1",
                    "empresa_id": "empresa-1",
                    "tipo_nf": "NFSe",
                    "numero_nf": "23",
                    "chave_acesso": "NFSExpto",
                    "xml_completo": "<nfse/>",
                    "xml_resumo": "",
                    "situacao": "autorizada",
                }
            ]
        }
    )

    response = await de.baixar_pdf_nota_empresa(
        empresa_id="empresa-1",
        nota_id="nota-1",
        download=False,
        permitir_fallback=False,
        usuario={"id": "user-1"},
        db=db,
    )
    content = await _read_stream(response)

    assert content.startswith(b"%PDF-1.4")
    assert response.headers.get("X-HiControl-Pdf-Source") == "official"


@pytest.mark.asyncio
async def test_baixar_pdf_nfse_sem_oficial_sem_fallback_retorna_404(fake_db_factory, monkeypatch):
    async def _validar(*_args, **_kwargs):
        return {"id": "empresa-1"}

    async def _pdf_oficial(*_args, **_kwargs):
        return None

    def _fallback(*_args, **_kwargs):
        raise AssertionError("Nao deveria gerar fallback sem permitir_fallback=true")

    monkeypatch.setattr(de, "_validar_empresa_usuario", _validar)
    monkeypatch.setattr(de, "_obter_pdf_oficial_nota", _pdf_oficial)
    monkeypatch.setattr(de, "_gerar_pdf_nota", _fallback)

    db = fake_db_factory(
        {
            "notas_fiscais": [
                {"id": "nota-1", "empresa_id": "empresa-1", "tipo_nf": "NFSe", "numero_nf": "23"}
            ]
        }
    )

    with pytest.raises(HTTPException) as exc:
        await de.baixar_pdf_nota_empresa(
            empresa_id="empresa-1",
            nota_id="nota-1",
            download=False,
            permitir_fallback=False,
            usuario={"id": "user-1"},
            db=db,
        )
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_baixar_pdf_nfse_com_fallback_gera_pdf_auxiliar(fake_db_factory, monkeypatch):
    async def _validar(*_args, **_kwargs):
        return {"id": "empresa-1"}

    async def _pdf_oficial(*_args, **_kwargs):
        return None

    def _fallback(*_args, **_kwargs):
        return b"%PDF-1.4 fallback"

    monkeypatch.setattr(de, "_validar_empresa_usuario", _validar)
    monkeypatch.setattr(de, "_obter_pdf_oficial_nota", _pdf_oficial)
    monkeypatch.setattr(de, "_gerar_pdf_nota", _fallback)

    db = fake_db_factory(
        {
            "notas_fiscais": [
                {"id": "nota-1", "empresa_id": "empresa-1", "tipo_nf": "NFSe", "numero_nf": "23"}
            ]
        }
    )

    response = await de.baixar_pdf_nota_empresa(
        empresa_id="empresa-1",
        nota_id="nota-1",
        download=False,
        permitir_fallback=True,
        usuario={"id": "user-1"},
        db=db,
    )
    content = await _read_stream(response)
    assert content.startswith(b"%PDF-1.4")
    assert response.headers.get("X-HiControl-Pdf-Source") == "generated"
