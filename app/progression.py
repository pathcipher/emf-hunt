"""Strict puzzle progression — the single source of truth.

A team's *current puzzle* is the lowest-ordered published puzzle it has NOT solved.
A team may view solved puzzles and the current one; everything ahead is locked.
All of this is enforced server-side; the UI never grants access on its own.
"""
from __future__ import annotations

from .models import Puzzle, Team


def published_puzzles() -> list[Puzzle]:
    return (
        Puzzle.query.filter_by(is_published=True)
        .order_by(Puzzle.order_index.asc())
        .all()
    )


def solved_puzzle_ids(team: Team | None) -> set[int]:
    if team is None:
        return set()
    return {solve.puzzle_id for solve in team.solves}


def current_puzzle(team: Team | None) -> Puzzle | None:
    """First published puzzle the team hasn't solved, or None if all are solved."""
    solved = solved_puzzle_ids(team)
    for puzzle in published_puzzles():
        if puzzle.id not in solved:
            return puzzle
    return None


def has_finished(team: Team | None) -> bool:
    """True when there is at least one puzzle and the team has solved them all."""
    return bool(published_puzzles()) and current_puzzle(team) is None


def can_access(team: Team | None, puzzle: Puzzle) -> bool:
    """A team may access solved puzzles and its current puzzle — nothing ahead."""
    if not puzzle.is_published:
        return False
    current = current_puzzle(team)
    if current is None:
        # Finished (or nothing locked): all published puzzles are viewable.
        return True
    return puzzle.order_index <= current.order_index
