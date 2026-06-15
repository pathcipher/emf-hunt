"""Cloudflare Turnstile verification for the login form.

When ``TURNSTILE_SECRET_KEY`` is unset the CAPTCHA is disabled (so local dev and
the test suite work without keys); verification then always "passes".
"""
from __future__ import annotations

import logging

import requests
from flask import current_app

logger = logging.getLogger("emf_hunt.captcha")

_VERIFY_URL = "https://challenges.cloudflare.com/turnstile/v0/siteverify"


def turnstile_enabled() -> bool:
    return bool(current_app.config.get("TURNSTILE_SECRET_KEY"))


def verify_turnstile(token: str | None) -> bool:
    """Return True if the Turnstile token is valid (or the CAPTCHA is disabled)."""
    secret = current_app.config.get("TURNSTILE_SECRET_KEY")
    if not secret:
        return True  # disabled
    if not token:
        return False
    try:
        resp = requests.post(
            _VERIFY_URL,
            data={"secret": secret, "response": token},
            timeout=5,
        )
        return bool(resp.json().get("success"))
    except Exception as exc:  # network error, malformed response, etc.
        logger.warning("Turnstile verification failed: %s", exc)
        return False
