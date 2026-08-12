"""Tests for the Chainlit UI: auth, chat profile -> domain mapping, on_message
orchestration, and REST routes preserved after mounting Chainlit into FastAPI."""

from __future__ import annotations

import os
from typing import ClassVar
from unittest.mock import AsyncMock, Mock

os.environ.setdefault("CHAINLIT_AUTH_SECRET", "test-secret")
os.environ.setdefault("APP_USERNAME", "gefin")
os.environ.setdefault("APP_PASSWORD", "s3cret")

import pytest
from fastapi.testclient import TestClient

from app import chainlit_app


class _FakeUserSession:
    def __init__(self, initial: dict | None = None) -> None:
        self._data = dict(initial or {})

    def get(self, key, default=None):
        return self._data.get(key, default)

    def set(self, key, value) -> None:
        self._data[key] = value


class _FakeMessage:
    sent: ClassVar[list[_FakeMessage]] = []

    def __init__(self, content, elements=None, **kwargs) -> None:
        self.content = content
        self.elements = elements or []

    async def send(self) -> None:
        _FakeMessage.sent.append(self)


def test_auth_callback_accepts_correct_credentials() -> None:
    user = chainlit_app.auth_callback("gefin", "s3cret")
    assert user is not None
    assert user.identifier == "gefin"


def test_auth_callback_rejects_incorrect_credentials() -> None:
    assert chainlit_app.auth_callback("gefin", "wrong-password") is None
    assert chainlit_app.auth_callback("someone-else", "s3cret") is None


@pytest.mark.asyncio
async def test_on_chat_start_defaults_to_ar_domain(monkeypatch) -> None:
    fake_session = _FakeUserSession({"chat_profile": None})
    monkeypatch.setattr(chainlit_app.cl, "user_session", fake_session)

    await chainlit_app.on_chat_start()

    assert fake_session.get("domain") == "ar"


@pytest.mark.asyncio
async def test_on_chat_start_maps_fabric_profile(monkeypatch) -> None:
    fake_session = _FakeUserSession({"chat_profile": "fabric"})
    monkeypatch.setattr(chainlit_app.cl, "user_session", fake_session)

    await chainlit_app.on_chat_start()

    assert fake_session.get("domain") == "fabric"


@pytest.mark.asyncio
async def test_on_message_calls_run_agent_with_callback_config_and_writes_audit(
    monkeypatch,
) -> None:
    fake_session = _FakeUserSession({"id": "sess-123", "domain": "ar"})
    monkeypatch.setattr(chainlit_app.cl, "user_session", fake_session)
    monkeypatch.setattr(chainlit_app.cl, "Message", _FakeMessage)
    monkeypatch.setattr(chainlit_app.cl, "LangchainCallbackHandler", lambda **_: "handler")
    _FakeMessage.sent.clear()

    fake_result = {
        "answer": "O saldo total em aberto é R$ 1.000.000.",
        "data": None,
        "chart_spec": None,
        "lineage": None,
        "plan": "Consultou catálogo",
        "tools_called": [],
        "final_sql": None,
        "steps": ["step_1"],
        "latency_ms": 123,
    }
    mock_run_agent = AsyncMock(return_value=fake_result)
    mock_write_audit = Mock()
    monkeypatch.setattr(chainlit_app, "run_agent", mock_run_agent)
    monkeypatch.setattr(chainlit_app, "write_audit", mock_write_audit)

    incoming = _FakeMessage(content="Qual o saldo total em aberto?")
    await chainlit_app.on_message(incoming)

    mock_run_agent.assert_awaited_once_with(
        user_message="Qual o saldo total em aberto?",
        session_id="sess-123",
        domain="ar",
        config={"callbacks": ["handler"]},
    )
    assert len(_FakeMessage.sent) == 1
    assert "R$ 1.000.000" in _FakeMessage.sent[0].content
    mock_write_audit.assert_called_once()
    assert mock_write_audit.call_args.kwargs["session_id"] == "sess-123"


def test_render_lineage_markdown_includes_views_and_sql() -> None:
    lineage = {
        "layer": "gold",
        "source_system": "ERP",
        "views": [{"view": "vw_ar_open_items", "description": "Itens em aberto"}],
        "sql": "SELECT 1",
    }
    md = chainlit_app._render_lineage_markdown(lineage)
    assert md is not None
    assert "vw_ar_open_items" in md
    assert "SELECT 1" in md


def test_render_lineage_markdown_returns_none_without_lineage() -> None:
    assert chainlit_app._render_lineage_markdown(None) is None


def test_health_and_catalog_routes_respond_after_mounting_chainlit() -> None:
    from app.main import app

    with TestClient(app) as client:
        health = client.get("/health")
        assert health.status_code == 200
        assert health.json()["status"] == "ok"

        catalog = client.get("/catalog")
        assert catalog.status_code == 200
