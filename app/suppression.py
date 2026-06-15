"""Email suppression list — addresses that complained or hard-bounced.

Populated by the SES/SNS webhook (see app/webhooks.py). The login flow checks
this before sending so we never re-mail someone who reported us as spam, which
is what keeps the SES account in good standing.
"""
from __future__ import annotations

from .extensions import db
from .models import Suppression


def _norm(email: str) -> str:
    return (email or "").strip().lower()


def is_suppressed(email: str) -> bool:
    addr = _norm(email)
    if not addr:
        return False
    return db.session.get(Suppression, addr) is not None


def suppress(email: str, reason: str) -> None:
    """Add an address to the suppression list (idempotent)."""
    addr = _norm(email)
    if not addr:
        return
    if db.session.get(Suppression, addr) is None:
        db.session.add(Suppression(email=addr, reason=reason[:40]))
        db.session.commit()


def unsuppress(email: str) -> bool:
    """Remove an address from the list. Returns True if one was removed."""
    row = db.session.get(Suppression, _norm(email))
    if row is None:
        return False
    db.session.delete(row)
    db.session.commit()
    return True
