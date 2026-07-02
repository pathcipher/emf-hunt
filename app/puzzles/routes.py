"""Player-facing puzzle flow with strict, server-enforced progression."""
from __future__ import annotations

from flask import (
    Blueprint,
    abort,
    flash,
    redirect,
    render_template,
    request,
    send_from_directory,
    url_for,
)
from flask_login import current_user, login_required
from markupsafe import escape
from sqlalchemy.exc import IntegrityError

from ..content import get_puzzle_content
from ..extensions import db, limiter
from ..media import puzzle_media_dir
from ..models import Puzzle, Solve, Submission
from ..progression import (
    can_access,
    current_puzzle,
    has_finished,
    parallel_mode,
    published_puzzles,
    solved_puzzle_ids,
)
from ..security import answers_match
from ..settings import DEFAULT_SUCCESS_HTML, SUCCESS_HTML, get_setting
from .forms import AnswerForm

bp = Blueprint("puzzles", __name__)


@bp.route("/")
@login_required
def index():
    if current_user.team_id is None:
        return redirect(url_for("teams.setup"))

    team = current_user.team

    if parallel_mode():
        return _parallel_index(team)

    puzzle = current_puzzle(team)
    if puzzle is None:
        if has_finished(team):
            return render_template(
                "puzzles/finished.html",
                team=team,
                success_html=render_success_html(team),
            )
        return render_template("puzzles/none.html")
    return redirect(url_for("puzzles.view", order=puzzle.order_index))


def _parallel_index(team):
    """Parallel mode: a filterable list of every published puzzle at once."""
    pubs = published_puzzles()
    if not pubs:
        return render_template("puzzles/none.html")

    solved = solved_puzzle_ids(team)
    active_tag = (request.args.get("tag") or "").strip()
    all_tags = sorted({t for p in pubs for t in p.get_tags()}, key=str.lower)

    if active_tag:
        shown = [
            p for p in pubs
            if any(t.lower() == active_tag.lower() for t in p.get_tags())
        ]
    else:
        shown = pubs

    items = [
        {"puzzle": p, "solved": p.id in solved, "tags": p.get_tags()} for p in shown
    ]
    finished = has_finished(team)
    return render_template(
        "puzzles/list.html",
        items=items,
        all_tags=all_tags,
        active_tag=active_tag,
        solved_count=sum(1 for p in pubs if p.id in solved),
        total=len(pubs),
        finished=finished,
        success_html=render_success_html(team) if finished else None,
    )


def render_success_html(team) -> str:
    """The admin-customised success page, with a safely-escaped team-name token.

    The HTML is trusted (admin-authored). The only untrusted value is the team
    name, so it is HTML-escaped before being substituted into the {{team_name}}
    placeholder — never injected raw into the |safe blob.
    """
    raw = get_setting(SUCCESS_HTML, "") or DEFAULT_SUCCESS_HTML
    return raw.replace("{{team_name}}", str(escape(team.name)))


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
    bg_image_url = (
        url_for("puzzles.media", puzzle_id=puzzle.id, filename=puzzle.bg_image)
        if puzzle.bg_image else None
    )
    return render_template(
        "puzzles/view.html",
        puzzle=puzzle,
        content_html=content_html,
        form=AnswerForm(),
        already_solved=puzzle.id in solved_ids,
        total=len(published_puzzles()),
        solved_count=len(solved_ids),
        parallel=parallel_mode(),
        bg_image_url=bg_image_url,
    )


@bp.route("/media/puzzle/<int:puzzle_id>/<path:filename>")
@login_required
def media(puzzle_id: int, filename: str):
    """Serve a puzzle's uploaded image, gated like the puzzle itself.

    A team can only fetch media for a puzzle it may already reach (solved or
    current). Admins may always fetch, so they can preview while authoring.
    """
    puzzle = db.session.get(Puzzle, puzzle_id)
    if puzzle is None:
        abort(404)

    team = current_user.team if current_user.team_id else None
    if not current_user.is_admin and not can_access(team, puzzle):
        abort(403)

    # send_from_directory safe-joins, so `filename` can't traverse out.
    return send_from_directory(puzzle_media_dir(puzzle_id), filename)


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

    if parallel_mode():
        # Every published puzzle is open; just enforce that it's reachable.
        if not can_access(team, puzzle):
            abort(403)
    else:
        # Sequential: answers are only accepted for the team's *current* puzzle.
        current = current_puzzle(team)
        if current is None or puzzle.id != current.id:
            abort(403)

    # Already solved (reachable in parallel mode) — nothing more to do.
    if Solve.query.filter_by(team_id=team.id, puzzle_id=puzzle.id).first():
        return redirect(url_for("puzzles.view", order=order))

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
