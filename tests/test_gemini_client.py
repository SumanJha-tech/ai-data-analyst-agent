import logging
from types import SimpleNamespace

import httpx
import pytest
from google.genai import errors as genai_errors

import gemini_client
from gemini_client import (
    call_gemini, GeminiUnavailable, GeminiNotConfigured, GeminiRequestError,
    BUSY_MESSAGE, RETRY_DELAYS,
)

# Captured at import, before the autouse fixture replaces it.
_REAL_GET_CLIENT = gemini_client._get_client


def api_error(code, status, message="boom"):
    cls = genai_errors.ServerError if code >= 500 else genai_errors.ClientError
    return cls(code, {"error": {"code": code, "message": message, "status": status}})


def ok(text="SELECT 1"):
    return SimpleNamespace(text=text)


class FakeClient:
    """models.generate_content pops scripted outcomes (exception instances are raised)."""
    def __init__(self, script):
        self.script = script
        self.calls = []
        self.models = SimpleNamespace(generate_content=self._generate)

    def _generate(self, model, contents, **kwargs):
        self.calls.append(model)
        outcome = self.script(model) if callable(self.script) else self.script.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


@pytest.fixture
def use_client(monkeypatch):
    def install(script):
        client = FakeClient(script)
        monkeypatch.setattr(gemini_client, "_get_client", lambda: client)
        return client
    return install


@pytest.fixture
def sleeps(monkeypatch):
    recorded = []
    monkeypatch.setattr(gemini_client, "_sleep", recorded.append)
    return recorded


def test_success_after_503(use_client, sleeps):
    client = use_client([api_error(503, "UNAVAILABLE"), ok("hello")])
    assert call_gemini("hi", model="primary") == "hello"
    assert client.calls == ["primary", "primary"]
    assert len(sleeps) == 1


def test_backoff_is_exponential_with_three_retries(use_client, sleeps):
    client = use_client(lambda model: api_error(503, "UNAVAILABLE"))
    with pytest.raises(GeminiUnavailable):
        call_gemini("hi", model="primary")
    assert len(client.calls) == 4  # first try + 3 retries
    assert len(sleeps) == 3
    for delay, base in zip(sleeps, RETRY_DELAYS):
        assert base * 0.7 <= delay <= base * 1.3


@pytest.mark.parametrize("code,status", [(429, "RESOURCE_EXHAUSTED"), (500, "INTERNAL")])
def test_other_transient_codes_are_retried(use_client, code, status):
    client = use_client([api_error(code, status), ok()])
    assert call_gemini("hi", model="primary") == "SELECT 1"
    assert len(client.calls) == 2


@pytest.mark.parametrize("exc", [httpx.ReadTimeout("slow"), httpx.ConnectError("down"), ConnectionError("reset")])
def test_timeouts_and_connection_errors_are_retried(use_client, exc):
    client = use_client([exc, ok()])
    assert call_gemini("hi", model="primary") == "SELECT 1"
    assert len(client.calls) == 2


def test_all_retries_fail_then_fallback_model_answers(use_client, sleeps, monkeypatch):
    monkeypatch.setenv("GEMINI_FALLBACK_MODEL", "backup-model")
    monkeypatch.setattr(gemini_client, "list_available_models", lambda: {"primary", "backup-model"})
    client = use_client(lambda model: api_error(503, "UNAVAILABLE") if model == "primary" else ok("from backup"))

    assert call_gemini("hi", model="primary") == "from backup"
    assert client.calls == ["primary"] * 4 + ["backup-model"]


def test_fallback_not_available_for_key_is_skipped(use_client, monkeypatch):
    monkeypatch.setenv("GEMINI_FALLBACK_MODEL", "ghost-model")
    monkeypatch.setattr(gemini_client, "list_available_models", lambda: {"primary"})
    client = use_client(lambda model: api_error(503, "UNAVAILABLE"))

    with pytest.raises(GeminiUnavailable):
        call_gemini("hi", model="primary")
    assert "ghost-model" not in client.calls


def test_primary_and_fallback_both_fail(use_client, monkeypatch):
    monkeypatch.setenv("GEMINI_FALLBACK_MODEL", "backup-model")
    monkeypatch.setattr(gemini_client, "list_available_models", lambda: {"primary", "backup-model"})
    use_client(lambda model: api_error(503, "UNAVAILABLE"))

    with pytest.raises(GeminiUnavailable) as info:
        call_gemini("hi", model="primary")
    assert str(info.value) == BUSY_MESSAGE
    assert "503" not in str(info.value) and "UNAVAILABLE" not in str(info.value)


def test_400_is_not_retried_and_does_not_fall_back(use_client, sleeps, monkeypatch):
    monkeypatch.setenv("GEMINI_FALLBACK_MODEL", "backup-model")
    monkeypatch.setattr(gemini_client, "list_available_models", lambda: {"primary", "backup-model"})
    client = use_client([api_error(400, "INVALID_ARGUMENT", "bad prompt")])

    with pytest.raises(GeminiRequestError):
        call_gemini("hi", model="primary")
    assert client.calls == ["primary"]
    assert sleeps == []


def test_invalid_api_key_is_not_retried(use_client, sleeps):
    client = use_client([api_error(400, "INVALID_ARGUMENT", "API key not valid. Please pass a valid API key.")])
    with pytest.raises(GeminiNotConfigured) as info:
        call_gemini("hi", model="primary")
    assert "not configured" in str(info.value)
    assert len(client.calls) == 1 and sleeps == []


def test_missing_api_key_raises_not_configured(monkeypatch):
    # Use the real _get_client (undo the autouse refusal) with no key anywhere.
    monkeypatch.setattr(gemini_client, "_get_client", _REAL_GET_CLIENT)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.setattr(gemini_client, "get_setting", lambda name: None)
    with pytest.raises(GeminiNotConfigured):
        call_gemini("hi", model="primary")


def test_empty_or_blocked_response_is_not_retried(use_client, sleeps):
    client = use_client([SimpleNamespace(text=None)])
    with pytest.raises(GeminiRequestError):
        call_gemini("hi", model="primary")
    assert len(client.calls) == 1 and sleeps == []


def test_api_key_never_appears_in_logs(use_client, monkeypatch, caplog):
    secret = "AIzaSy-SECRET-KEY-VALUE"
    monkeypatch.setenv("GEMINI_API_KEY", secret)
    use_client(lambda model: api_error(503, "UNAVAILABLE", f"upstream said key {secret} overloaded"))
    with caplog.at_level(logging.DEBUG):
        with pytest.raises(GeminiUnavailable):
            call_gemini("hi", model="primary")
    assert secret not in caplog.text
    assert caplog.text  # the technical error is logged, just scrubbed


def test_sql_retry_is_separate_from_network_retry(monkeypatch):
    import ask
    replies = iter(["SELECT * FROM table_that_does_not_exist", "SELECT 1 AS x"])
    monkeypatch.setattr(ask, "call_gemini", lambda prompt, model=None: next(replies))
    sql, df = ask.ask_question("anything")
    assert sql == "SELECT 1 AS x" and df["x"].tolist() == [1]
