from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.v1.endpoints import drive_import_endpoints
from app.dependencies import get_current_user
from app.services.google_drive_service import google_drive_service


def _build_client():
    app = FastAPI()
    app.include_router(drive_import_endpoints.router, prefix="/api/v1")
    app.dependency_overrides[get_current_user] = lambda: {"id": "user-1"}
    return TestClient(app)


def test_auth_url_retorna_503_quando_google_nao_configurado(monkeypatch):
    monkeypatch.delenv("GOOGLE_CLIENT_ID", raising=False)
    monkeypatch.delenv("GOOGLE_REDIRECT_URI", raising=False)
    client = _build_client()

    resp = client.get("/api/v1/drive/auth/url")
    assert resp.status_code == 503
    body = resp.json()
    assert body["detail"]["error"] == "google_not_configured"


def test_auth_url_retorna_url_quando_configurado(monkeypatch):
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "client-id")
    monkeypatch.setenv("GOOGLE_REDIRECT_URI", "https://callback")
    monkeypatch.setattr(google_drive_service, "gerar_url_autorizacao", lambda state: f"https://oauth?state={state}")
    client = _build_client()

    resp = client.get("/api/v1/drive/auth/url")
    assert resp.status_code == 200
    assert resp.json()["url"].startswith("https://oauth")


def test_exportacao_xml_massa_iniciar(monkeypatch):
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "client-id")
    monkeypatch.setenv("GOOGLE_REDIRECT_URI", "https://callback")

    async def _mock_iniciar(user_id, empresa_ids=None, filtros=None):
        assert user_id == "user-1"
        assert empresa_ids == ["empresa-1"]
        assert filtros == {"tipo": "NFE"}
        return {
            "id": "job-1",
            "status": "processando",
            "total_notas": 10,
            "notas_processadas": 2,
            "notas_exportadas": 2,
            "notas_duplicadas": 0,
            "notas_erro": 0,
            "progresso_percentual": 20,
            "mensagem": "iniciando",
            "pasta_raiz_id": "drive-root",
            "created_at": "2026-03-07T10:00:00Z",
            "updated_at": "2026-03-07T10:00:01Z",
        }

    monkeypatch.setattr(google_drive_service, "iniciar_exportacao_xml_massa", _mock_iniciar)
    client = _build_client()

    resp = client.post(
        "/api/v1/drive/exportacoes/xmls/iniciar",
        json={"empresa_ids": ["empresa-1"], "filtros": {"tipo": "NFE"}},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == "job-1"
    assert body["status"] == "processando"
    assert body["total_notas"] == 10


def test_exportacao_xml_massa_status(monkeypatch):
    async def _mock_status(job_id, user_id):
        assert job_id == "job-1"
        assert user_id == "user-1"
        return {
            "id": "job-1",
            "status": "concluido",
            "total_notas": 5,
            "notas_processadas": 5,
            "notas_exportadas": 5,
            "notas_duplicadas": 0,
            "notas_erro": 0,
            "progresso_percentual": 100,
            "mensagem": "ok",
            "pasta_raiz_id": "root",
            "created_at": "2026-03-07T10:00:00Z",
            "updated_at": "2026-03-07T10:01:00Z",
        }

    monkeypatch.setattr(google_drive_service, "obter_status_exportacao", _mock_status)
    client = _build_client()

    resp = client.get("/api/v1/drive/exportacoes/xmls/job-1")
    assert resp.status_code == 200
    assert resp.json()["status"] == "concluido"


def test_sincronizar_pastas_clientes(monkeypatch):
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "client-id")
    monkeypatch.setenv("GOOGLE_REDIRECT_URI", "https://callback")

    async def _mock_sync(user_id, empresa_ids=None, config=None):
        assert user_id == "user-1"
        assert empresa_ids == ["empresa-1", "empresa-2"]
        return {"pastas_criadas": 2, "pastas_atualizadas": 0}

    monkeypatch.setattr(google_drive_service, "sincronizar_pastas_clientes", _mock_sync)
    client = _build_client()

    resp = client.post(
        "/api/v1/drive/pastas/sincronizar-clientes",
        json=["empresa-1", "empresa-2"],
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["sucesso"] is True
    assert body["pastas_criadas"] == 2
