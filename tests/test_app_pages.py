"""Boots every page with Gemini forced to fail (503) and checks the app degrades gracefully."""
from pathlib import Path
from types import SimpleNamespace

import pytest
from google.genai import errors as genai_errors
from streamlit.testing.v1 import AppTest

import gemini_client

APP_FILE = Path(__file__).resolve().parent.parent / "app.py"
PAGES = ["🏠 Dashboard", "💬 Chat Analyst", "🔍 Anomaly Radar", "📁 My Data", "📖 Dataset Overview"]
UNMATCHED = "Which seller has the most orders in Minas Gerais in 2018?"


@pytest.fixture(autouse=True)
def broken_gemini(monkeypatch):
    def always_503(**kwargs):
        raise genai_errors.ServerError(503, {"error": {"code": 503, "status": "UNAVAILABLE",
                                                       "message": "This model is currently experiencing high demand."}})
    client = SimpleNamespace(models=SimpleNamespace(generate_content=always_503))
    monkeypatch.setattr(gemini_client, "_get_client", lambda: client)


def new_app():
    import streamlit as st
    st.cache_data.clear()  # the 60s AI-status cache must not leak between tests
    at = AppTest.from_file(str(APP_FILE), default_timeout=120)
    at.run()
    assert not at.exception
    return at


def page_text(at):
    parts = [m.value for m in at.markdown] + [i.value for i in at.info] + [e.value for e in at.error]
    return " ".join(str(p) for p in parts)


def test_sidebar_badge_reflects_outage():
    text = page_text(new_app())
    assert "AI busy, demo mode" in text
    assert "Gemini AI Ready" not in text


@pytest.mark.parametrize("page", PAGES)
def test_every_page_opens_without_exceptions(page):
    at = new_app()
    at.session_state["page"] = page
    at.run()
    assert not at.exception
    assert "503" not in page_text(at)


def test_try_one_of_these_returns_saved_answer():
    at = new_app()
    at.button(key="ex_5").click().run()
    assert not at.exception
    turn = at.session_state["chat_history"][-1]
    assert turn["demo"] is True and turn["error"] is None
    assert len(turn["df"]) == 5
    text = page_text(at)
    assert "Demo answer (live AI unavailable)" in text
    assert "503" not in text and "UNAVAILABLE" not in text and 'class="status-err"' not in text


def test_unmatched_question_gets_friendly_message_and_suggestions():
    at = new_app()
    at.session_state["page"] = "💬 Chat Analyst"
    at.run()
    at.chat_input[0].set_value(UNMATCHED).run()
    assert not at.exception
    turn = at.session_state["chat_history"][-1]
    assert turn["demo"] is False and "The AI is busy right now" in turn["error"]
    assert len(turn["suggestions"]) == 4
    text = page_text(at)
    assert "503" not in text and "UNAVAILABLE" not in text and 'class="status-err"' not in text

    # a suggestion button works in demo mode too
    at.button(key="sug_0_0").click().run()
    assert at.session_state["chat_history"][-1]["demo"] is True


def test_anomaly_radar_shows_real_findings_without_ai():
    at = new_app()
    at.session_state["page"] = "🔍 Anomaly Radar"
    at.run()
    at.button[0].click().run()
    assert not at.exception
    text = page_text(at)
    assert "AI summary is unavailable" in text and "503" not in text
