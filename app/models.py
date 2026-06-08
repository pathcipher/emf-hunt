"""Database models.

Notes on security-relevant fields:
- User has **no password column** — login is via magic link only.
- Puzzle.answer and Puzzle.content_html live only in the DB (never the repo).
- LoginToken stores a *hash* of the token, never the raw token, and is single-use.
"""
from __future__ import annotations

import secrets
from datetime import datetime, timezone

from flask_login import UserMixin

from .extensions import db

# Unambiguous join-code alphabet (no 0/O/1/I).
_CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def generate_join_code(length: int = 6) -> str:
    return "".join(secrets.choice(_CODE_ALPHABET) for _ in range(length))


class User(UserMixin, db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    display_name = db.Column(db.String(80))
    is_admin = db.Column(db.Boolean, default=False, nullable=False)
    team_id = db.Column(db.Integer, db.ForeignKey("teams.id"), nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)

    team = db.relationship("Team", back_populates="members", foreign_keys=[team_id])


class Team(db.Model):
    __tablename__ = "teams"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), unique=True, nullable=False)
    join_code = db.Column(db.String(12), unique=True, nullable=False, index=True)
    # use_alter breaks the users<->teams FK cycle for clean create/drop ordering.
    created_by_id = db.Column(
        db.Integer, db.ForeignKey("users.id", use_alter=True, name="fk_team_created_by")
    )
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)

    members = db.relationship("User", back_populates="team", foreign_keys=[User.team_id])
    created_by = db.relationship("User", foreign_keys=[created_by_id])
    solves = db.relationship(
        "Solve", back_populates="team", cascade="all, delete-orphan"
    )


class Puzzle(db.Model):
    __tablename__ = "puzzles"

    id = db.Column(db.Integer, primary_key=True)
    # order_index defines the strict sequence players walk through.
    order_index = db.Column(db.Integer, unique=True, nullable=False, index=True)
    title = db.Column(db.String(160), nullable=False)
    content_html = db.Column(db.Text, nullable=False, default="")
    answer = db.Column(db.String(255), nullable=False, default="")
    is_published = db.Column(db.Boolean, default=False, nullable=False)
    # Optional remote handler URL for dynamic puzzle content. If set, content is
    # fetched from this URL instead of using stored content_html.
    handler_url = db.Column(db.String(500), nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at = db.Column(
        db.DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )


class Solve(db.Model):
    __tablename__ = "solves"

    id = db.Column(db.Integer, primary_key=True)
    team_id = db.Column(db.Integer, db.ForeignKey("teams.id"), nullable=False)
    puzzle_id = db.Column(db.Integer, db.ForeignKey("puzzles.id"), nullable=False)
    solved_by_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    solved_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)

    __table_args__ = (
        db.UniqueConstraint("team_id", "puzzle_id", name="uq_team_puzzle"),
    )

    team = db.relationship("Team", back_populates="solves")
    puzzle = db.relationship("Puzzle")
    solved_by = db.relationship("User")


class Submission(db.Model):
    """Every answer attempt — audit trail + powers rate limiting and admin insight."""

    __tablename__ = "submissions"

    id = db.Column(db.Integer, primary_key=True)
    team_id = db.Column(db.Integer, db.ForeignKey("teams.id"), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    puzzle_id = db.Column(db.Integer, db.ForeignKey("puzzles.id"), nullable=False)
    text = db.Column(db.String(255), nullable=False)
    is_correct = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)

    team = db.relationship("Team")
    user = db.relationship("User")
    puzzle = db.relationship("Puzzle")


class LoginToken(db.Model):
    """Single-use, expiring magic-link token. Only the hash is stored."""

    __tablename__ = "login_tokens"

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), nullable=False, index=True)
    token_hash = db.Column(db.String(64), unique=True, nullable=False, index=True)
    expires_at = db.Column(db.DateTime(timezone=True), nullable=False)
    used_at = db.Column(db.DateTime(timezone=True), nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)
