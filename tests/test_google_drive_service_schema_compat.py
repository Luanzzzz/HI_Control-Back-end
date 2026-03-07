from __future__ import annotations

import pytest
from postgrest.exceptions import APIError

from app.services.google_drive_service import GoogleDriveService


class _Result:
    def __init__(self, data):
        self.data = data


class _Query:
    def __init__(self, table, mode):
        self._table = table
        self._mode = mode

    def select(self, fields):
        self._table.last_select = fields
        return self

    def eq(self, *_args, **_kwargs):
        return self

    def order(self, *_args, **_kwargs):
        return self

    def execute(self):
        if self._mode == "new":
            raise APIError(
                {
                    "message": "column configuracoes_drive.pasta_raiz_export_id does not exist",
                    "code": "42703",
                }
            )
        return _Result(
            [
                {
                    "id": "cfg-1",
                    "user_id": "user-1",
                    "empresa_id": "emp-1",
                    "provedor": "google_drive",
                    "pasta_id": "pasta-1",
                    "pasta_nome": "Notas",
                    "ultima_sincronizacao": None,
                    "total_importadas": 0,
                    "ativo": True,
                    "created_at": "2026-03-07T10:00:00Z",
                    "updated_at": "2026-03-07T10:00:00Z",
                }
            ]
        )


class _Table:
    def __init__(self):
        self.calls = 0
        self.last_select = ""

    def select(self, fields):
        self.calls += 1
        mode = "new" if self.calls == 1 else "legacy"
        query = _Query(self, mode=mode)
        return query.select(fields)


class _DB:
    def __init__(self):
        self.table_obj = _Table()

    def table(self, _name):
        return self.table_obj


@pytest.mark.asyncio
async def test_listar_configuracoes_fallback_quando_colunas_novas_ausentes(monkeypatch):
    fake_db = _DB()

    def _fake_get_admin():
        return fake_db

    monkeypatch.setattr("app.db.supabase_client.get_supabase_admin", _fake_get_admin)

    service = GoogleDriveService()
    rows = await service.listar_configuracoes("user-1")

    assert len(rows) == 1
    assert rows[0]["id"] == "cfg-1"
    assert rows[0]["pasta_raiz_export_id"] is None
    assert rows[0]["pasta_raiz_export_nome"] is None
    assert fake_db.table_obj.calls == 2
