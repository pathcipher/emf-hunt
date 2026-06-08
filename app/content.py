"""Dynamic puzzle content fetching and caching."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

import requests
from flask import current_app

logger = logging.getLogger("emf_hunt.content")

# Cache: {(puzzle_id, team_id): (content_html, expires_at)}
_content_cache: dict[tuple[int, int], tuple[str, datetime]] = {}


def get_puzzle_content(puzzle_id: int, team_id: int, handler_url: str) -> str:
    """Fetch puzzle content from a remote handler URL with caching.

    If the handler URL is not set or fetching fails, returns empty string.
    Caches responses for PUZZLE_CONTENT_CACHE_SECONDS (default 60).
    """
    cache_key = (puzzle_id, team_id)
    now = datetime.now(timezone.utc)

    # Check cache
    if cache_key in _content_cache:
        content, expires_at = _content_cache[cache_key]
        if expires_at > now:
            logger.debug(f"Cache hit for puzzle {puzzle_id} team {team_id}")
            return content

    if not handler_url:
        return ""

    try:
        cache_seconds = current_app.config.get("PUZZLE_CONTENT_CACHE_SECONDS", 60)
        resp = requests.get(
            handler_url,
            params={"puzzle_id": puzzle_id, "team_id": team_id, "at": now.isoformat()},
            timeout=5,
        )
        resp.raise_for_status()
        content = resp.text

        # Cache the response
        expires_at = now + timedelta(seconds=cache_seconds)
        _content_cache[cache_key] = (content, expires_at)
        logger.debug(f"Fetched and cached content for puzzle {puzzle_id} team {team_id}")

        return content
    except Exception as e:
        logger.warning(f"Failed to fetch puzzle content from {handler_url}: {e}")
        return ""


def clear_content_cache() -> None:
    """Clear the puzzle content cache (useful for testing or manual refresh)."""
    _content_cache.clear()
