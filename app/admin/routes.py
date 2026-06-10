"""Admin: dashboard, puzzle authoring (HTML editor), and team progress."""
from __future__ import annotations

from flask import (
    Blueprint,
    abort,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    url_for,
)
from flask_login import login_required

from ..extensions import db
from ..media import (
    delete_puzzle_media,
    list_puzzle_media,
    save_puzzle_media,
)
from ..models import Puzzle, Submission, Team, User, generate_join_code
from ..progression import current_puzzle, published_puzzles
from ..security import admin_required
from .forms import MediaUploadForm, PuzzleForm

bp = Blueprint("admin", __name__, url_prefix="/admin")


def _sort_ts(dt) -> float:
    return dt.timestamp() if dt is not None else 0.0


@bp.route("/")
@login_required
@admin_required
def dashboard():
    stats = {
        "puzzles": Puzzle.query.count(),
        "published": Puzzle.query.filter_by(is_published=True).count(),
        "teams": Team.query.count(),
        "players": User.query.count(),
        "submissions": Submission.query.count(),
    }
    return render_template("admin/dashboard.html", stats=stats)


@bp.route("/puzzles")
@login_required
@admin_required
def puzzles():
    items = Puzzle.query.order_by(Puzzle.order_index.asc()).all()
    return render_template("admin/puzzles.html", puzzles=items)


@bp.route("/puzzles/new", methods=["GET", "POST"])
@login_required
@admin_required
def puzzle_new():
    form = PuzzleForm()
    if form.validate_on_submit():
        if Puzzle.query.filter_by(order_index=form.order_index.data).first():
            flash("A puzzle already uses that order number.", "error")
        else:
            db.session.add(
                Puzzle(
                    order_index=form.order_index.data,
                    title=form.title.data.strip(),
                    content_html=form.content_html.data or "",
                    answer=form.answer.data.strip(),
                    is_published=form.is_published.data,
                )
            )
            db.session.commit()
            flash("Puzzle created.", "success")
            return redirect(url_for("admin.puzzles"))
    return render_template("admin/puzzle_form.html", form=form, mode="new")


@bp.route("/puzzles/<int:puzzle_id>/edit", methods=["GET", "POST"])
@login_required
@admin_required
def puzzle_edit(puzzle_id: int):
    puzzle = db.session.get(Puzzle, puzzle_id)
    if puzzle is None:
        abort(404)

    form = PuzzleForm(obj=puzzle)
    if form.validate_on_submit():
        clash = Puzzle.query.filter(
            Puzzle.order_index == form.order_index.data, Puzzle.id != puzzle.id
        ).first()
        if clash:
            flash("Another puzzle already uses that order number.", "error")
        else:
            puzzle.order_index = form.order_index.data
            puzzle.title = form.title.data.strip()
            puzzle.content_html = form.content_html.data or ""
            puzzle.answer = form.answer.data.strip()
            puzzle.is_published = form.is_published.data
            db.session.commit()
            flash("Puzzle saved.", "success")
            return redirect(url_for("admin.puzzles"))
    return render_template(
        "admin/puzzle_form.html",
        form=form,
        mode="edit",
        puzzle=puzzle,
        media_form=MediaUploadForm(),
        media_files=list_puzzle_media(puzzle.id),
    )


@bp.route("/puzzles/<int:puzzle_id>/media", methods=["POST"])
@login_required
@admin_required
def puzzle_media_upload(puzzle_id: int):
    puzzle = db.session.get(Puzzle, puzzle_id)
    if puzzle is None:
        abort(404)

    form = MediaUploadForm()
    if not form.validate_on_submit():
        flash("Upload failed (invalid request).", "error")
        return redirect(url_for("admin.puzzle_edit", puzzle_id=puzzle_id))

    saved, errors = 0, []
    for file in form.files.data or []:
        if not file or not file.filename:
            continue
        name, error = save_puzzle_media(puzzle_id, file)
        if error:
            errors.append(error)
        else:
            saved += 1

    if saved:
        flash(f"Uploaded {saved} image{'s' if saved != 1 else ''}.", "success")
    for error in errors:
        flash(error, "error")
    if not saved and not errors:
        flash("No files selected.", "error")
    return redirect(url_for("admin.puzzle_edit", puzzle_id=puzzle_id))


@bp.route("/puzzles/<int:puzzle_id>/media/delete", methods=["POST"])
@login_required
@admin_required
def puzzle_media_delete(puzzle_id: int):
    puzzle = db.session.get(Puzzle, puzzle_id)
    if puzzle is None:
        abort(404)
    # CSRF is enforced by Flask-WTF on this POST via the hidden token in the form.
    filename = (request.form.get("filename") or "").strip()
    if delete_puzzle_media(puzzle_id, filename):
        flash(f"Deleted “{filename}”.", "success")
    else:
        flash("Could not delete that file.", "error")
    return redirect(url_for("admin.puzzle_edit", puzzle_id=puzzle_id))


@bp.route("/progress")
@login_required
@admin_required
def progress():
    total = len(published_puzzles())
    rows = []
    for team in Team.query.order_by(Team.name.asc()).all():
        last = max((s.solved_at for s in team.solves), default=None)
        rows.append(
            {
                "team": team,
                "solved": len(team.solves),
                "total": total,
                "current": current_puzzle(team),
                "last_solved_at": last,
                "members": team.members,
            }
        )
    rows.sort(key=lambda r: (r["solved"], _sort_ts(r["last_solved_at"])), reverse=True)
    return render_template("admin/progress.html", rows=rows, total=total)


def _filtered_submissions(args):
    """Build a Submission query from request filters. Returns (query, team, puzzle, result)."""
    query = Submission.query
    team_id = args.get("team", type=int)
    puzzle_id = args.get("puzzle", type=int)
    result = args.get("result", "all")

    if team_id:
        query = query.filter(Submission.team_id == team_id)
    if puzzle_id:
        query = query.filter(Submission.puzzle_id == puzzle_id)
    if result == "correct":
        query = query.filter(Submission.is_correct.is_(True))
    elif result == "wrong":
        query = query.filter(Submission.is_correct.is_(False))
    else:
        result = "all"
    return query, team_id, puzzle_id, result


def _serialize_submission(s: Submission) -> dict:
    # All values are emitted as JSON strings; the client renders them via
    # textContent (never innerHTML), so player-supplied text can't inject markup.
    return {
        "id": s.id,
        "time": s.created_at.strftime("%H:%M:%S"),
        "team": s.team.name if s.team else "—",
        "player": (s.user.display_name or s.user.email) if s.user else "—",
        "puzzle": f"#{s.puzzle.order_index}" if s.puzzle else "—",
        "text": s.text,
        "correct": bool(s.is_correct),
    }


@bp.route("/submissions")
@login_required
@admin_required
def submissions():
    query, team_id, puzzle_id, result = _filtered_submissions(request.args)
    recent = query.order_by(Submission.id.desc()).limit(100).all()
    return render_template(
        "admin/submissions.html",
        submissions=recent,
        cursor=recent[0].id if recent else 0,
        teams=Team.query.order_by(Team.name.asc()).all(),
        puzzles=Puzzle.query.order_by(Puzzle.order_index.asc()).all(),
        sel_team=team_id,
        sel_puzzle=puzzle_id,
        sel_result=result,
    )


@bp.route("/submissions.json")
@login_required
@admin_required
def submissions_feed():
    """Submissions as JSON, filtered by the same team/puzzle/result params.

    - With ?after=<id>: incremental — only rows newer than <id> (live polling).
    - Without ?after:   snapshot — the newest matching rows, used to rebuild the
                        whole table when filters change.

    Rows are always returned oldest-first so the client can prepend each one and
    end up with newest-on-top.
    """
    after = request.args.get("after", type=int)
    query, _team, _puzzle, _result = _filtered_submissions(request.args)

    if after is None:
        rows = query.order_by(Submission.id.desc()).limit(100).all()
        rows.reverse()  # -> oldest-first
    else:
        rows = (
            query.filter(Submission.id > after)
            .order_by(Submission.id.asc())
            .limit(200)
            .all()
        )

    return jsonify(
        submissions=[_serialize_submission(s) for s in rows],
        cursor=rows[-1].id if rows else (after or 0),
    )


# --- Team administration ---------------------------------------------------

def _member_label(user: User) -> str:
    return user.display_name or user.email


def _redirect_after_member_action():
    """Return to the team page the action came from, else the teams list."""
    rt = request.form.get("return_team", "")
    if rt.isdigit() and db.session.get(Team, int(rt)) is not None:
        return redirect(url_for("admin.team_detail", team_id=int(rt)))
    return redirect(url_for("admin.teams"))


@bp.route("/teams")
@login_required
@admin_required
def teams():
    total = len(published_puzzles())
    rows = [
        {
            "team": team,
            "members": len(team.members),
            "solved": len(team.solves),
            "current": current_puzzle(team),
        }
        for team in Team.query.order_by(Team.name.asc()).all()
    ]
    unassigned = User.query.filter_by(team_id=None).order_by(User.email.asc()).all()
    return render_template(
        "admin/teams.html",
        rows=rows,
        total=total,
        unassigned=unassigned,
        all_teams=Team.query.order_by(Team.name.asc()).all(),
    )


@bp.route("/teams/<int:team_id>")
@login_required
@admin_required
def team_detail(team_id: int):
    team = db.session.get(Team, team_id)
    if team is None:
        abort(404)
    return render_template(
        "admin/team_detail.html",
        team=team,
        other_teams=Team.query.filter(Team.id != team.id).order_by(Team.name.asc()).all(),
        current=current_puzzle(team),
        solved=len(team.solves),
        total=len(published_puzzles()),
    )


@bp.route("/teams/<int:team_id>/rename", methods=["POST"])
@login_required
@admin_required
def team_rename(team_id: int):
    team = db.session.get(Team, team_id)
    if team is None:
        abort(404)
    name = (request.form.get("name") or "").strip()
    if not (2 <= len(name) <= 80):
        flash("Team name must be 2–80 characters.", "error")
    elif Team.query.filter(Team.name == name, Team.id != team.id).first():
        flash("That team name is taken.", "error")
    else:
        team.name = name
        db.session.commit()
        flash("Team renamed.", "success")
    return redirect(url_for("admin.team_detail", team_id=team.id))


@bp.route("/teams/<int:team_id>/regenerate-code", methods=["POST"])
@login_required
@admin_required
def team_regen_code(team_id: int):
    team = db.session.get(Team, team_id)
    if team is None:
        abort(404)
    code = generate_join_code()
    while Team.query.filter_by(join_code=code).first():
        code = generate_join_code()
    team.join_code = code
    db.session.commit()
    flash("New join code generated.", "success")
    return redirect(url_for("admin.team_detail", team_id=team.id))


@bp.route("/teams/<int:team_id>/delete", methods=["POST"])
@login_required
@admin_required
def team_delete(team_id: int):
    team = db.session.get(Team, team_id)
    if team is None:
        abort(404)
    name = team.name
    for member in list(team.members):  # unassign members (clears the FK)
        member.team_id = None
    Submission.query.filter_by(team_id=team.id).delete()  # solves cascade with team
    db.session.delete(team)
    db.session.commit()
    flash(f"Deleted team “{name}”.", "success")
    return redirect(url_for("admin.teams"))


@bp.route("/members/<int:user_id>/move", methods=["POST"])
@login_required
@admin_required
def member_move(user_id: int):
    user = db.session.get(User, user_id)
    if user is None:
        abort(404)
    raw = (request.form.get("team_id") or "").strip()
    if raw == "":
        user.team_id = None
        db.session.commit()
        flash(f"Removed {_member_label(user)} from their team.", "success")
    elif raw.isdigit() and (target := db.session.get(Team, int(raw))) is not None:
        user.team_id = target.id
        db.session.commit()
        flash(f"Moved {_member_label(user)} to {target.name}.", "success")
    else:
        flash("No such team.", "error")
    return _redirect_after_member_action()


@bp.route("/members/<int:user_id>/toggle-admin", methods=["POST"])
@login_required
@admin_required
def member_toggle_admin(user_id: int):
    user = db.session.get(User, user_id)
    if user is None:
        abort(404)
    if user.is_admin:
        if User.query.filter_by(is_admin=True).count() <= 1:
            flash("Can't remove the last admin.", "error")
        else:
            user.is_admin = False
            db.session.commit()
            flash(f"{_member_label(user)} is no longer an admin.", "success")
    else:
        user.is_admin = True
        db.session.commit()
        flash(f"{_member_label(user)} is now an admin.", "success")
    return _redirect_after_member_action()
