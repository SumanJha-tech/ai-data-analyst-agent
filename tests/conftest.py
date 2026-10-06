import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import gemini_client  # noqa: E402


@pytest.fixture(autouse=True)
def isolate_gemini(monkeypatch):
    """Tests must never reach the real Gemini API or wait on real backoff."""
    def refuse():
        raise RuntimeError("test tried to create a real Gemini client")

    monkeypatch.setattr(gemini_client, "_get_client", refuse)
    monkeypatch.setattr(gemini_client, "_sleep", lambda s: None)
    monkeypatch.delenv("GEMINI_FALLBACK_MODEL", raising=False)
    monkeypatch.setitem(gemini_client._model_cache, "models", None)
    yield
