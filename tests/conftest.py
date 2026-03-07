from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import pytest


@dataclass
class FakeExecuteResult:
    data: List[Dict[str, Any]]
    count: Optional[int] = None


class FakeSupabaseQuery:
    def __init__(self, rows: List[Dict[str, Any]]):
        self._rows = rows
        self._filters: Dict[str, Any] = {}
        self._range_start: Optional[int] = None
        self._range_end: Optional[int] = None

    def select(self, *_args, **_kwargs):
        return self

    def eq(self, field: str, value: Any):
        self._filters[field] = value
        return self

    def gte(self, _field: str, _value: Any):
        return self

    def lt(self, _field: str, _value: Any):
        return self

    def in_(self, _field: str, _value: Any):
        return self

    def order(self, *_args, **_kwargs):
        return self

    def or_(self, *_args, **_kwargs):
        return self

    def limit(self, _value: int):
        return self

    def range(self, start: int, end: int):
        self._range_start = start
        self._range_end = end
        return self

    def execute(self) -> FakeExecuteResult:
        filtered = [
            row
            for row in self._rows
            if all(row.get(k) == v for k, v in self._filters.items())
        ]
        if self._range_start is not None and self._range_end is not None:
            filtered = filtered[self._range_start : self._range_end + 1]
        return FakeExecuteResult(data=filtered, count=len(filtered))


class FakeSupabaseClient:
    def __init__(self, table_rows: Dict[str, List[Dict[str, Any]]]):
        self._table_rows = table_rows

    def table(self, name: str) -> FakeSupabaseQuery:
        return FakeSupabaseQuery(self._table_rows.get(name, []))


@pytest.fixture
def fake_db_factory():
    def _factory(table_rows: Dict[str, List[Dict[str, Any]]]) -> FakeSupabaseClient:
        return FakeSupabaseClient(table_rows)

    return _factory
