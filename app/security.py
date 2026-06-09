"""Security helpers: magic-link tokens, answer normalization, admin gate."""
from __future__ import annotations

import hashlib
import re
import secrets
from datetime import timezone
from functools import wraps

from flask import abort, current_app
from flask_login import current_user

from .extensions import db
from .models import LoginToken, utcnow

_WHITESPACE = re.compile(r"\s+")


def normalize_answer(text: str) -> str:
    """Canonicalise an answer for comparison: trim, collapse whitespace, lowercase.

    Admins should set answers knowing this normalization is applied to both the
    stored answer and the player's submission before comparing.
    """
    return _WHITESPACE.sub(" ", (text or "").strip()).lower()


def answers_match(submitted: str, stored: str | list[str]) -> bool:
    """Check if a submitted answer matches any of the stored answers.

    Args:
        submitted: Player's answer (will be normalized).
        stored: One or more acceptable answers. Can be a single string or list of strings.

    Returns:
        True if the submitted answer matches any of the stored answers (after normalization).
    """
    normalized_submitted = normalize_answer(submitted)

    # Handle both single string and list of strings
    if isinstance(stored, str):
        stored_list = [stored]
    else:
        stored_list = stored

    return any(normalize_answer(ans) == normalized_submitted for ans in stored_list)


def _hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def create_login_token(email: str) -> str:
    """Create a single-use magic-link token, returning the *raw* token to email."""
    raw = secrets.token_urlsafe(32)
    token = LoginToken(
        email=email.strip().lower(),
        token_hash=_hash_token(raw),
        expires_at=utcnow() + current_app.config["MAGIC_LINK_MAX_AGE"],
    )
    db.session.add(token)
    db.session.commit()
    return raw


def consume_login_token(raw: str) -> str | None:
    """Validate and burn a token. Returns the email on success, else None."""
    token = LoginToken.query.filter_by(token_hash=_hash_token(raw)).first()
    if token is None or token.used_at is not None:
        return None

    expires = token.expires_at
    if expires.tzinfo is None:  # SQLite hands datetimes back naive
        expires = expires.replace(tzinfo=timezone.utc)
    if expires < utcnow():
        return None

    token.used_at = utcnow()
    db.session.commit()
    return token.email


def admin_required(view):
    """Gate a view to authenticated admins (403 otherwise)."""

    @wraps(view)
    def wrapped(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin:
            abort(403)
        return view(*args, **kwargs)

    return wrapped
