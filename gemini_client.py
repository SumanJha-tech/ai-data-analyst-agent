"""Single entry point for every Gemini call in the app.

Responsibilities: lazy client creation (no key -> no crash at import), retry
with exponential backoff on transient errors, fallback to a second model, and
translation of raw API errors into three small exception types whose messages
are safe to show to a user. The real technical error is only ever logged.
"""
import logging
import os
import random
import time

import httpx
from google import genai
from google.genai import errors as genai_errors
from google.genai import types

logger = logging.getLogger(__name__)

PRIMARY_MODEL = "gemini-3.6-flash"

# Base delays for the 3 retries (~1s, 3s, 7s); each gets +/-25% jitter.
RETRY_DELAYS = (1.0, 3.0, 7.0)
REQUEST_TIMEOUT_MS = 30_000
STATUS_TIMEOUT_MS = 10_000
MODEL_LIST_TTL_SECONDS = 3600

TRANSIENT_CODES = {429, 500, 502, 503, 504}
TRANSIENT_STATUSES = {"UNAVAILABLE", "RESOURCE_EXHAUSTED", "INTERNAL", "DEADLINE_EXCEEDED"}

BUSY_MESSAGE = ("The AI is busy right now. Please try again in a few seconds, "
                "or try one of the demo questions below.")
NOT_CONFIGURED_MESSAGE = "The AI service is not configured. You can still explore the demo questions below."
REQUEST_FAILED_MESSAGE = ("The AI couldn't answer that one. Try rephrasing the question, "
                          "or try one of the demo questions below.")


class GeminiError(Exception):
    """Base class. str(error) is always a short, user-safe message."""
    user_message = BUSY_MESSAGE

    def __init__(self, technical_detail=""):
        super().__init__(self.user_message)
        self.technical_detail = technical_detail


class GeminiUnavailable(GeminiError):
    """Transient failure that outlasted all retries and the fallback model."""
    user_message = BUSY_MESSAGE


class GeminiNotConfigured(GeminiError):
    """API key missing or rejected."""
    user_message = NOT_CONFIGURED_MESSAGE


class GeminiRequestError(GeminiError):
    """Permanent failure for this request (bad request, safety block, empty reply)."""
    user_message = REQUEST_FAILED_MESSAGE


# Injectable so tests don't actually wait.
_sleep = time.sleep

_client_cache = {}
_model_cache = {"fetched_at": 0.0, "models": None}


def get_setting(name):
    """Environment variable first, then st.secrets (Streamlit Cloud)."""
    value = os.environ.get(name)
    if value:
        return value
    try:
        import streamlit as st
        value = st.secrets.get(name)
        return str(value) if value else None
    except Exception:
        return None


def _api_key():
    return get_setting("GEMINI_API_KEY") or get_setting("GOOGLE_API_KEY")


def _get_client():
    key = _api_key()
    if not key:
        raise GeminiNotConfigured("No GEMINI_API_KEY / GOOGLE_API_KEY set")
    if key not in _client_cache:
        _client_cache.clear()
        _client_cache[key] = genai.Client(
            api_key=key, http_options=types.HttpOptions(timeout=REQUEST_TIMEOUT_MS)
        )
    return _client_cache[key]


def _scrub(text):
    """Never let the key reach a log line."""
    key = _api_key()
    return text.replace(key, "***") if key and text else text


def classify_error(exc):
    """Returns 'transient', 'auth', 'model_missing' or 'permanent'."""
    if isinstance(exc, GeminiError):
        return "auth" if isinstance(exc, GeminiNotConfigured) else "permanent"

    if isinstance(exc, genai_errors.APIError):
        code = getattr(exc, "code", None)
        status = (getattr(exc, "status", None) or "").upper()
        text = str(exc).lower()
        if code in TRANSIENT_CODES or status in TRANSIENT_STATUSES:
            return "transient"
        if code in (401, 403) or status in ("UNAUTHENTICATED", "PERMISSION_DENIED") \
                or "api key" in text or "api_key" in text:
            return "auth"
        if code == 404 or status == "NOT_FOUND":
            return "model_missing"
        return "permanent"

    if isinstance(exc, (httpx.TimeoutException, httpx.TransportError, TimeoutError, ConnectionError)):
        return "transient"
    if isinstance(exc, ValueError) and "api key" in str(exc).lower():
        return "auth"
    return "permanent"


def _backoff_delay(attempt):
    return RETRY_DELAYS[attempt] * random.uniform(0.75, 1.25)


def _generate(client, model, prompt):
    response = client.models.generate_content(model=model, contents=prompt)
    text = response.text
    if not text or not text.strip():
        # Safety block or empty candidate: retrying the same prompt won't help.
        raise GeminiRequestError("Empty or blocked response from model")
    return text.strip()


def _call_with_retries(client, model, prompt, delays):
    """Returns text, or raises the last underlying exception once retries are
    exhausted. Permanent errors are raised immediately, never retried."""
    for attempt in range(len(delays) + 1):
        try:
            return _generate(client, model, prompt)
        except Exception as exc:
            kind = classify_error(exc)
            if kind != "transient" or attempt == len(delays):
                raise
            delay = _backoff_delay(attempt)
            logger.warning("Gemini %s transient error (attempt %d/%d), retrying in %.1fs: %s",
                           model, attempt + 1, len(delays) + 1, delay, _scrub(f"{type(exc).__name__}: {exc}"))
            _sleep(delay)


def list_available_models():
    """Model ids usable for generateContent with the configured key, cached for
    an hour. Returns None if the listing itself fails."""
    now = time.time()
    if _model_cache["models"] is not None and now - _model_cache["fetched_at"] < MODEL_LIST_TTL_SECONDS:
        return _model_cache["models"]
    try:
        names = set()
        for m in _get_client().models.list():
            actions = m.supported_actions or []
            if not actions or "generateContent" in actions:
                names.add((m.name or "").removeprefix("models/"))
        _model_cache.update(fetched_at=now, models=names)
        return names
    except Exception as exc:
        logger.warning("Could not list Gemini models: %s", _scrub(f"{type(exc).__name__}: {exc}"))
        return None


def get_fallback_model(primary=PRIMARY_MODEL):
    """Configured fallback model, or None if unset, same as primary, or not
    offered for this API key."""
    name = get_setting("GEMINI_FALLBACK_MODEL")
    if not name or name == primary:
        return None
    available = list_available_models()
    if available is not None and name not in available:
        logger.warning("Fallback model %s is not available for this API key; ignoring it", name)
        return None
    return name


def call_gemini(prompt, model=PRIMARY_MODEL):
    """Send `prompt` to Gemini and return the reply text.

    Transient errors are retried 3 times with backoff, then the fallback model
    gets the same treatment. Raises GeminiUnavailable, GeminiNotConfigured or
    GeminiRequestError; the real error is logged, never put in the message.
    """
    client = _get_client()

    candidates = [model]
    last_exc = None
    tried_fallback = False

    while candidates:
        current = candidates.pop(0)
        try:
            return _call_with_retries(client, current, prompt, RETRY_DELAYS)
        except GeminiError as exc:
            logger.error("Gemini request error on %s: %s", current, _scrub(exc.technical_detail))
            raise
        except Exception as exc:
            last_exc = exc
            kind = classify_error(exc)
            logger.error("Gemini call failed on %s (%s): %s", current, kind,
                         _scrub(f"{type(exc).__name__}: {exc}"))
            if kind == "auth":
                raise GeminiNotConfigured(str(exc)) from None
            if kind == "permanent":
                raise GeminiRequestError(str(exc)) from None
            # transient (retries exhausted) or model_missing: try the fallback once
            if not tried_fallback:
                tried_fallback = True
                fallback = get_fallback_model(model)
                if fallback:
                    logger.warning("Switching to fallback model %s", fallback)
                    candidates.append(fallback)

    if classify_error(last_exc) == "model_missing":
        raise GeminiRequestError(str(last_exc)) from None
    raise GeminiUnavailable(str(last_exc)) from None


def check_ai_status(model=PRIMARY_MODEL):
    """Lightweight health probe: one tiny generate call, no retries.
    Returns 'ready', 'busy' or 'not_configured'. Callers should cache this."""
    try:
        client = _get_client()
    except GeminiError:
        return "not_configured"

    models = [model]
    fallback_checked = False
    for attempt_model in models:
        try:
            client.models.generate_content(
                model=attempt_model, contents="ping",
                config=types.GenerateContentConfig(
                    max_output_tokens=8,
                    http_options=types.HttpOptions(timeout=STATUS_TIMEOUT_MS)),
            )
            return "ready"
        except Exception as exc:
            kind = classify_error(exc)
            logger.warning("Gemini status check failed on %s (%s): %s", attempt_model, kind,
                           _scrub(f"{type(exc).__name__}: {exc}"))
            if kind == "auth":
                return "not_configured"
            if kind in ("transient", "model_missing") and not fallback_checked:
                fallback_checked = True
                fallback = get_fallback_model(model)
                if fallback:
                    models.append(fallback)
    return "busy"
