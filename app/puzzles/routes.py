"""Player-facing puzzle flow with strict, server-enforced progression."""
from __future__ import annotations

from flask import (
    Blueprint,
    abort,
    flash,
    redirect,
    render_template,
    url_for,
)
from flask_login import current_user, login_required
from sqlalchemy.exc import IntegrityError

from ..content import get_puzzle_content
from ..extensions import db, limiter
from ..models import Puzzle, Solve, Submission
from ..progression import (
    can_access,
    current_puzzle,
    has_finished,
    published_puzzles,
)
from ..security import answers_match
from .forms import AnswerForm

bp = Blueprint("puzzles", __name__)


@bp.route("/")
@login_required
def index():
    if current_user.team_id is None:
        return redirect(url_for("teams.setup"))

    team = current_user.team
    puzzle = current_puzzle(team)
    if puzzle is None:
        if has_finished(team):
            return render_template("puzzles/finished.html", team=team)
        return render_template("puzzles/none.html")
    return redirect(url_for("puzzles.view", order=puzzle.order_index))


@bp.route("/puzzle/<int:order>")
@login_required
def view(order: int):
    if current_user.team_id is None:
        return redirect(url_for("teams.setup"))

    team = current_user.team
    puzzle = Puzzle.query.filter_by(order_index=order).first_or_404()
    if not can_access(team, puzzle):
        abort(403)  # future puzzle — locked

    # Fetch dynamic content if handler_url is set; otherwise use stored content.
    content_html = puzzle.content_html
    if puzzle.handler_url:
        dynamic_content = get_puzzle_content(puzzle.id, team.id, puzzle.handler_url)
        if dynamic_content:
            content_html = dynamic_content

    solved_ids = {solve.puzzle_id for solve in team.solves}
    return render_template(
        "puzzles/view.html",
        puzzle=puzzle,
        content_html=content_html,
        form=AnswerForm(),
        already_solved=puzzle.id in solved_ids,
        total=len(published_puzzles()),
        solved_count=len(solved_ids),
    )


def _answer_rate_key() -> str:
    # Rate-limit answer attempts per *team* (NAT-safe on shared camp wifi).
    if current_user.is_authenticated and current_user.team_id:
        return f"team:{current_user.team_id}"
    return f"user:{getattr(current_user, 'id', 'anon')}"


@bp.route("/puzzle/<int:order>/submit", methods=["POST"])
@login_required
@limiter.limit("20 per minute", key_func=_answer_rate_key)
def submit(order: int):
    if current_user.team_id is None:
        return redirect(url_for("teams.setup"))

    team = current_user.team
    puzzle = Puzzle.query.filter_by(order_index=order).first_or_404()

    # Answers are only accepted for the team's *current* puzzle.
    current = current_puzzle(team)
    if current is None or puzzle.id != current.id:
        abort(403)

    form = AnswerForm()
    if not form.validate_on_submit():
        flash("Please enter an answer.", "error")
        return redirect(url_for("puzzles.view", order=order))

    attempt = form.answer.data.strip()
    correct = answers_match(attempt, puzzle.get_answers())

    # Record every attempt (audit trail) — commit it independently.
    db.session.add(
        Submission(
            team_id=team.id,
            user_id=current_user.id,
            puzzle_id=puzzle.id,
            text=attempt[:255],
            is_correct=correct,
        )
    )
    db.session.commit()

    if not correct:
        flash("Not quite — try again.", "error")
        return redirect(url_for("puzzles.view", order=order))

    # Correct: record the solve, tolerating a teammate's concurrent solve.
    if Solve.query.filter_by(team_id=team.id, puzzle_id=puzzle.id).first() is None:
        db.session.add(
            Solve(team_id=team.id, puzzle_id=puzzle.id, solved_by_id=current_user.id)
        )
        try:
            db.session.commit()
        except IntegrityError:
            db.session.rollback()  # unique(team, puzzle) — already solved

    flash("Correct! On to the next one.", "success")
    return redirect(url_for("puzzles.index"))
