"""Unit-test fixtures for the API component: app with a stubbed DB.

No network, no postgres. The DB dependency is replaced with a FIFO queue of
canned results; every executed statement is recorded for assertions.
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from fastapi.testclient import TestClient

from place.api import deps, security
from place.api.app import create_app


class FakeResult:
    def __init__(
        self,
        rows: list[dict[str, Any]] | None = None,
        rowcount: int | None = None,
        scalar_value: Any = None,
    ) -> None:
        self.rows = [dict(r) for r in (rows or [])]
        self.rowcount = len(self.rows) if rowcount is None else rowcount
        self._scalar = scalar_value

    def mappings(self) -> FakeResult:
        return self

    def all(self) -> list[dict[str, Any]]:
        return self.rows

    def first(self) -> dict[str, Any] | None:
        return self.rows[0] if self.rows else None

    def fetchall(self) -> list[dict[str, Any]]:
        return self.rows

    def scalar(self) -> Any:
        if self._scalar is not None:
            return self._scalar
        if self.rows:
            return next(iter(self.rows[0].values()))
        return None


class FakeSavepoint:
    async def commit(self) -> None:
        pass

    async def rollback(self) -> None:
        pass


class FakeDb:
    def __init__(self) -> None:
        self.results: list[Any] = []
        self.calls: list[tuple[Any, Any]] = []

    def queue(self, *results: Any) -> FakeDb:
        self.results.extend(results)
        return self

    async def execute(self, stmt: Any, params: Any = None) -> FakeResult:
        self.calls.append((stmt, params))
        item = self.results.pop(0) if self.results else FakeResult()
        if isinstance(item, Exception):
            raise item
        return item

    async def begin_nested(self) -> FakeSavepoint:
        return FakeSavepoint()

    def inserts_into(self, table_name: str) -> list[Any]:
        """Compiled params of every INSERT into the named table."""
        out = []
        for stmt, _ in self.calls:
            table = getattr(stmt, "table", None)
            if (
                table is not None
                and getattr(table, "name", None) == table_name
                and stmt.__visit_name__ == "insert"
            ):
                out.append(stmt.compile().params)
        return out


@pytest.fixture(autouse=True)
def _fresh_api_settings(monkeypatch: pytest.MonkeyPatch):
    security.get_api_settings.cache_clear()
    yield
    security.get_api_settings.cache_clear()


@pytest.fixture()
def fake_db() -> FakeDb:
    return FakeDb()


@pytest.fixture()
def unit_app(fake_db: FakeDb):
    app = create_app()

    async def _get_db():
        return fake_db

    app.dependency_overrides[deps.get_db] = _get_db
    return app


@pytest.fixture()
def client(unit_app) -> TestClient:
    return TestClient(unit_app)


@pytest.fixture()
def user() -> dict[str, Any]:
    return {
        "id": uuid.uuid4(),
        "email": "swimmer@example.com",
        "display_name": "swimmer",
        "power_verifier": False,
    }


@pytest.fixture()
def auth_client(unit_app, user) -> TestClient:
    async def _user():
        return user

    unit_app.dependency_overrides[deps.get_current_user] = _user
    return TestClient(unit_app)
