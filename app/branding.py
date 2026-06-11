"""Customisable site branding: favicon and logo.

Unlike per-puzzle media, these are site-wide and **public** — they appear on
the login page before a visitor authenticates. Files live on the media volume
under ``MEDIA_ROOT/branding/`` and a pointer to the current filename is kept in
the ``settings`` table (key ``<kind>_file``).

Only one file is kept per kind: uploading replaces any previous one (including a
different extension). Like puzzle content, these are trusted admin-authored
assets (an SVG may carry script) — within the existing trust boundary.
"""
from __future__ import annotations

import glob
import os

from flask import Blueprint, abort, current_app, send_from_directory, url_for
from werkzeug.datastructures import FileStorage

from .settings import get_setting, set_setting

bp = Blueprint("branding", __name__)

# Allowed extensions per asset kind.
KINDS = {
    "favicon": {"ico", "png", "svg", "webp"},
    "logo": {"png", "jpg", "jpeg", "svg", "webp", "gif"},
}


def branding_dir(*, create: bool = False) -> str:
    path = os.path.join(current_app.config["MEDIA_ROOT"], "branding")
    if create:
        os.makedirs(path, exist_ok=True)
    return path


def get_branding_filename(kind: str) -> str | None:
    return get_setting(f"{kind}_file", "") or None


def _existing_path(kind: str) -> str | None:
    name = get_branding_filename(kind)
    if not name:
        return None
    path = os.path.join(branding_dir(), name)
    return path if os.path.isfile(path) else None


def save_branding(kind: str, file: FileStorage) -> tuple[str | None, str | None]:
    """Save the favicon/logo, replacing any previous file. Returns (name, error)."""
    allowed = KINDS.get(kind)
    if allowed is None:
        return None, "Unknown asset."
    raw = file.filename or ""
    if "." not in raw:
        return None, "File needs an extension."
    ext = raw.rsplit(".", 1)[1].lower()
    if ext not in allowed:
        return None, f"{kind} must be one of: {', '.join(sorted(allowed))}."

    directory = branding_dir(create=True)
    # Drop any previous file(s) for this kind so extensions can't pile up.
    for old in glob.glob(os.path.join(directory, f"{kind}.*")):
        try:
            os.remove(old)
        except OSError:
            pass

    name = f"{kind}.{ext}"
    file.save(os.path.join(directory, name))
    set_setting(f"{kind}_file", name)
    return name, None


def delete_branding(kind: str) -> None:
    if kind not in KINDS:
        return
    for old in glob.glob(os.path.join(branding_dir(), f"{kind}.*")):
        try:
            os.remove(old)
        except OSError:
            pass
    set_setting(f"{kind}_file", "")


def branding_url(kind: str) -> str | None:
    """Public URL for an asset, cache-busted by file mtime, or None if unset."""
    path = _existing_path(kind)
    if path is None:
        return None
    try:
        version = int(os.path.getmtime(path))
    except OSError:
        version = 0
    return f"{url_for('branding.serve', kind=kind)}?v={version}"


@bp.app_context_processor
def inject_branding():
    """Expose favicon_url / logo_url to every template (None when unset)."""
    try:
        return {
            "favicon_url": branding_url("favicon"),
            "logo_url": branding_url("logo"),
        }
    except Exception:  # never let branding break a page render
        return {"favicon_url": None, "logo_url": None}


@bp.get("/branding/<kind>")
def serve(kind: str):
    """Public: serve the current favicon/logo."""
    if kind not in KINDS:
        abort(404)
    name = get_branding_filename(kind)
    directory = branding_dir()
    if not name or not os.path.isfile(os.path.join(directory, name)):
        abort(404)
    resp = send_from_directory(directory, name)
    resp.headers["Cache-Control"] = "public, max-age=300"
    return resp


@bp.get("/favicon.ico")
def favicon():
    """Public: answer the browser's default favicon request, if one is set."""
    name = get_branding_filename("favicon")
    directory = branding_dir()
    if not name or not os.path.isfile(os.path.join(directory, name)):
        abort(404)
    return send_from_directory(directory, name)
