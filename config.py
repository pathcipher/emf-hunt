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

    # Cloudflare Turnstile (login CAPTCHA). When the secret is unset the CAPTCHA
    # is disabled (dev/test). Set both keys in production to require it.
    TURNSTILE_SITE_KEY = os.environ.get("TURNSTILE_SITE_KEY", "")
    TURNSTILE_SECRET_KEY = os.environ.get("TURNSTILE_SECRET_KEY", "")

    # SES bounce/complaint webhook (Amazon SNS). Optional topic-ARN allowlist;
    # signature verification is on by default and should stay on in production.
    SES_SNS_TOPIC_ARN = os.environ.get("SES_SNS_TOPIC_ARN", "")
    SES_WEBHOOK_VERIFY = _bool(os.environ.get("SES_WEBHOOK_VERIFY"), default=True)

    # Dynamic puzzle content cache duration (seconds).
    # Cache responses from handler URLs to reduce load on external services.
    PUZZLE_CONTENT_CACHE_SECONDS = int(os.environ.get("PUZZLE_CONTENT_CACHE_SECONDS", "60"))

    # Puzzle media (admin-uploaded images). Stored on disk, NOT in the repo or DB.
    # Defaults to a top-level media/ dir in dev; in Docker, point MEDIA_ROOT at a
    # mounted volume (e.g. /app/media). Served per-puzzle behind the same access
    # control as the puzzle itself.
    MEDIA_ROOT = os.environ.get("MEDIA_ROOT") or os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "media"
    )
    # Image types admins may upload. Note: SVG can carry inline script — that's
    # within the existing trust boundary (only admins upload), consistent with
    # admin-authored puzzle HTML/JS.
    MEDIA_ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "webp", "svg"}
    # Cap request bodies (applies to uploads too). Override with MAX_UPLOAD_MB.
    MAX_CONTENT_LENGTH = int(os.environ.get("MAX_UPLOAD_MB", "16")) * 1024 * 1024
