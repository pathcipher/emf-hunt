"""Puzzle media: admin-uploaded images stored on disk, served per-puzzle.

Files live under ``MEDIA_ROOT/puzzles/<puzzle_id>/<filename>`` — outside the repo
and the database. Access is gated by puzzle progression (see puzzles.media), so an
image is only reachable by a team that may already reach its puzzle.

Security notes:
- ``secure_filename`` strips any path components, so uploads can't escape the
  per-puzzle directory or traverse with ``..``.
- Serving uses Flask's ``send_from_directory`` (safe-join) — the canonical guard
  against path traversal on the read side.
- Only an extension allowlist is accepted (config ``MEDIA_ALLOWED_EXTENSIONS``).
"""
from __future__ import annotations

import os

from flask import current_app
from werkzeug.datastructures import FileStorage
from werkzeug.utils import secure_filename


def _media_root() -> str:
    return current_app.config["MEDIA_ROOT"]


def puzzle_media_dir(puzzle_id: int, *, create: bool = False) -> str:
    """Absolute path to a puzzle's media directory."""
    path = os.path.join(_media_root(), "puzzles", str(int(puzzle_id)))
    if create:
        os.makedirs(path, exist_ok=True)
    return path


def is_allowed_filename(filename: str) -> bool:
    if "." not in filename:
        return False
    ext = filename.rsplit(".", 1)[1].lower()
    return ext in current_app.config["MEDIA_ALLOWED_EXTENSIONS"]


def list_puzzle_media(puzzle_id: int) -> list[str]:
    """Sorted list of stored filenames for a puzzle (empty if none)."""
    directory = puzzle_media_dir(puzzle_id)
    if not os.path.isdir(directory):
        return []
    return sorted(
        name
        for name in os.listdir(directory)
        if os.path.isfile(os.path.join(directory, name))
    )


def save_puzzle_media(puzzle_id: int, file: FileStorage) -> tuple[str | None, str | None]:
    """Save one uploaded file, overwriting any existing file of the same name.

    Returns ``(saved_name, error)`` — exactly one is non-None.
    """
    raw = file.filename or ""
    name = secure_filename(raw)
    if not name:
        return None, f"“{raw}” has no usable filename."
    if not is_allowed_filename(name):
        allowed = ", ".join(sorted(current_app.config["MEDIA_ALLOWED_EXTENSIONS"]))
        return None, f"“{raw}” is not an allowed image type ({allowed})."

    directory = puzzle_media_dir(puzzle_id, create=True)
    file.save(os.path.join(directory, name))  # overwrites on same name
    return name, None


def delete_puzzle_media(puzzle_id: int, filename: str) -> bool:
    """Delete one file. Returns True if a file was removed."""
    name = secure_filename(filename or "")
    if not name:
        return False
    path = os.path.join(puzzle_media_dir(puzzle_id), name)
    # Defence in depth: ensure the resolved path stays inside the puzzle dir.
    directory = puzzle_media_dir(puzzle_id)
    if os.path.commonpath([os.path.abspath(path), os.path.abspath(directory)]) != os.path.abspath(directory):
        return False
    if os.path.isfile(path):
        os.remove(path)
        return True
    return False
