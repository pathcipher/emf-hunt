"""Application configuration, driven entirely by environment variables.

A single env-driven Config keeps dev and prod identical in code; the only
difference is the values in the environment (or .env in development).
"""
from __future__ import annotations

import os
from datetime import timedelta


def _bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


class Config:
    # Core
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-insecure-change-me")
    SQLALCHEMY_DATABASE_URI = os.environ.get("DATABASE_URL", "sqlite:///emf_hunt.db")
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Public base URL used to build absolute magic links.
    BASE_URL = os.environ.get("BASE_URL", "http://localhost:8000")

    # Display name shown across the UI and in emails.
    SITE_NAME = os.environ.get("SITE_NAME", "Pathcipher@EMF")

    # Contact details for the footer (optional; omitted if unset).
    CONTACT_NAME = os.environ.get("CONTACT_NAME", "")
    CONTACT_EMAIL = os.environ.get("CONTACT_EMAIL", "")
    CONTACT_PHONE = os.environ.get("CONTACT_PHONE", "")

    # Email delivery
    EMAIL_BACKEND = os.environ.get("EMAIL_BACKEND", "console")
    EMAIL_FROM = os.environ.get("EMAIL_FROM", "EMF Hunt <hunt@example.org>")
    EMAIL_API_URL = os.environ.get("EMAIL_API_URL", "")
    EMAIL_API_KEY = os.environ.get("EMAIL_API_KEY", "")

    # Magic-link lifetime (minutes).
    MAGIC_LINK_MAX_AGE = timedelta(
        minutes=int(os.environ.get("MAGIC_LINK_MINUTES", "15"))
    )

    # Session cookie hardening
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = _bool(os.environ.get("SESSION_COOKIE_SECURE"), default=False)
    PERMANENT_SESSION_LIFETIME = timedelta(days=7)

    # Rate-limit storage. memory:// is fine for a single-process camp deploy;
    # use redis:// if you run multiple workers.
    RATELIMIT_STORAGE_URI = os.environ.get("RATELIMIT_STORAGE_URI", "memory://")

    # Dynamic puzzle content cache duration (seconds).
    # Cache responses from handler URLs to reduce load on external services.
    PUZZLE_CONTENT_CACHE_SECONDS = int(os.environ.get("PUZZLE_CONTENT_CACHE_SECONDS", "60"))
