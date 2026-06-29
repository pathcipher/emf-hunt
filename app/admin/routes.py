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
from sqlalchemy import distinct, func

from ..extensions import db
from ..media import (
    delete_puzzle_media,
    list_puzzle_media,
    save_puzzle_media,
)
from ..branding import (
    KINDS as BRANDING_KINDS,
    delete_branding,
    get_branding_filename,
    save_branding,
)
from ..content import get_puzzle_content
from ..models import (
    Puzzle,
    Solve,
    Submission,
    Suppression,
    Team,
    User,
    generate_join_code,
)
from ..progression import current_puzzle, published_puzzles
from ..security import admin_required
from ..suppression import suppress, unsuppress
from ..settings import (
    DEFAULT_SUCCESS_HTML,
    PARALLEL_MODE_KEY,
    SUCCESS_HTML,
    get_setting,
    set_setting,
)
from .forms import BrandingUploadForm, MediaUploadForm, PuzzleForm, SuccessPageForm

bp = Blueprint("admin", __name__, url_prefix="/admin")


def _sort_ts(dt) -> float:
    return dt.timestamp() if dt is not None else 0.0


def _needs_answer(puzzle) -> bool:
    """True when a puzzle has no real answer set (empty, or just a '_' placeholder)."""
    return not any(a.strip() and a.strip() != "_" for a in puzzle.get_answers())


@bp.route("/")
@login_required
@admin_required
def dashboard():
    published_ids = [p.id for p in published_puzzles()]
    total_published = len(published_ids)

    # Teams that have made ≥1 guess / ≥1 solve.
    teams_with_guess = db.session.query(Submission.team_id).distinct().count()
    teams_with_solve = db.session.query(Solve.team_id).distinct().count()

    # Teams that have solved every published puzzle (100%).
    teams_full = 0
    if total_published:
        per_team = (
            db.session.query(func.count(distinct(Solve.puzzle_id)))
            .filter(Solve.puzzle_id.in_(published_ids))
            .group_by(Solve.team_id)
            .all()
        )
        teams_full = sum(1 for (solved,) in per_team if solved == total_published)

    stats = {
        "puzzles": Puzzle.query.count(),
        "published": total_published,
        "teams": Team.query.count(),
        "players": User.query.count(),
        "submissions": Submission.query.count(),
        "teams_with_guess": teams_with_guess,
        "teams_with_solve": teams_with_solve,
        "teams_full": teams_full,
    }
    return render_template("admin/dashboard.html", stats=stats)


@bp.route("/puzzles")
@login_required
@admin_required
def puzzles():
    items = Puzzle.query.order_by(Puzzle.order_index.asc()).all()
    total_teams = Team.query.count()

    # Per-puzzle: distinct teams that have guessed / solved it.
    started = dict(
        db.session.query(Submission.puzzle_id, func.count(distinct(Submission.team_id)))
        .group_by(Submission.puzzle_id)
        .all()
    )
    solved = dict(
        db.session.query(Solve.puzzle_id, func.count(distinct(Solve.team_id)))
        .group_by(Solve.puzzle_id)
        .all()
    )
    rows = [
        {
            "puzzle": p,
            "started": started.get(p.id, 0),
            "solved": solved.get(p.id, 0),
            "pct": round(100 * solved.get(p.id, 0) / total_teams) if total_teams else 0,
            "needs_answer": _needs_answer(p),
        }
        for p in items
    ]
    return render_template("admin/puzzles.html", rows=rows, total_teams=total_teams)


@bp.route("/puzzles/new", methods=["GET", "POST"])
@login_required
@admin_required
def puzzle_new():
    form = PuzzleForm()
    if form.validate_on_submit():
        if Puzzle.query.filter_by(order_index=form.order_index.data).first():
            flash("A puzzle already uses that order number.", "error")
        else:
            puzzle = Puzzle(
                order_index=form.order_index.data,
                title=form.title.data.strip(),
                content_html=form.content_html.data or "",
                answer=form.answer.data.strip(),
                tags=(form.tags.data or "").strip(),
                is_published=form.is_published.data,
            )
            db.session.add(puzzle)
            db.session.commit()
            flash("Puzzle created.", "success")
            # Continue on the new puzzle's edit page (so you can add images, etc.).
            return redirect(url_for("admin.puzzle_edit", puzzle_id=puzzle.id))
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
            puzzle.tags = (form.tags.data or "").strip()
            puzzle.is_published = form.is_published.data
            db.session.commit()
            flash("Puzzle saved.", "success")
            # Stay on the edit page so authoring is iterative (not back to the list).
            return redirect(url_for("admin.puzzle_edit", puzzle_id=puzzle.id))
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


@bp.route("/puzzles/<int:puzzle_id>/preview")
@login_required
@admin_required
def puzzle_preview(puzzle_id: int):
    """Render a puzzle exactly as players see it, bypassing the progression lock.

    Read-only: no answer form, the accepted answers are shown instead, and
    nothing is recorded. Works for unpublished or future puzzles.
    """
    puzzle = db.session.get(Puzzle, puzzle_id)
    if puzzle is None:
        abort(404)

    content_html = puzzle.content_html
    if puzzle.handler_url:
        # Faithful preview of dynamic content; team_id 0 if the admin has no team.
        dynamic = get_puzzle_content(puzzle.id, current_user.team_id or 0, puzzle.handler_url)
        if dynamic:
            content_html = dynamic

    return render_template(
        "puzzles/view.html",
        puzzle=puzzle,
        content_html=content_html,
        preview=True,
        answers=puzzle.get_answers(),
    )


@bp.route("/success-page", methods=["GET", "POST"])
@login_required
@admin_required
def success_page():
    """Edit the HTML shown to a team that has finished every puzzle."""
    form = SuccessPageForm()
    if form.validate_on_submit():
        set_setting(SUCCESS_HTML, form.content_html.data or "")
        flash("Success page saved.", "success")
        return redirect(url_for("admin.success_page"))
    if request.method == "GET":
        form.content_html.data = get_setting(SUCCESS_HTML, "")

    effective = (form.content_html.data or "").strip() or DEFAULT_SUCCESS_HTML
    return render_template(
        "admin/success_page.html",
        form=form,
        preview_html=effective.replace("{{team_name}}", "The Cartographers"),
    )


@bp.route("/branding")
@login_required
@admin_required
def branding():
    return render_template(
        "admin/branding.html",
        form=BrandingUploadForm(),
        favicon=get_branding_filename("favicon"),
        logo=get_branding_filename("logo"),
    )


@bp.route("/branding/<kind>", methods=["POST"])
@login_required
@admin_required
def branding_upload(kind: str):
    if kind not in BRANDING_KINDS:
        abort(404)
    form = BrandingUploadForm()
    if not form.validate_on_submit() or not form.file.data or not form.file.data.filename:
        flash("Choose a file to upload.", "error")
        return redirect(url_for("admin.branding"))
    _name, error = save_branding(kind, form.file.data)
    if error:
        flash(error, "error")
    else:
        flash(f"{kind.capitalize()} updated.", "success")
    return redirect(url_for("admin.branding"))


@bp.route("/branding/<kind>/delete", methods=["POST"])
@login_required
@admin_required
def branding_delete(kind: str):
    if kind not in BRANDING_KINDS:
        abort(404)
    delete_branding(kind)
    flash(f"{kind.capitalize()} removed.", "success")
    return redirect(url_for("admin.branding"))


@bp.route("/mode", methods=["POST"])
@login_required
@admin_required
def set_mode():
    """Toggle the event's progression mode (sequential ↔ parallel)."""
    parallel = request.form.get("parallel") == "on"
    set_setting(PARALLEL_MODE_KEY, "true" if parallel else "false")
    flash(
        "Parallel mode on — all published puzzles are open."
        if parallel
        else "Sequential mode on — one puzzle at a time.",
        "success",
    )
    return redirect(url_for("admin.dashboard"))


@bp.route("/suppressions")
@login_required
@admin_required
def suppressions():
    rows = Suppression.query.order_by(Suppression.created_at.desc()).all()
    return render_template("admin/suppressions.html", rows=rows)


@bp.route("/suppressions/remove", methods=["POST"])
@login_required
@admin_required
def suppression_remove():
    email = (request.form.get("email") or "").strip()
    if unsuppress(email):
        flash(f"Unblocked {email} — they can request login links again.", "success")
    else:
        flash("That address isn't on the blocklist.", "error")
    return redirect(url_for("admin.suppressions"))


@bp.route("/suppressions/add", methods=["POST"])
@login_required
@admin_required
def suppression_add():
    email = (request.form.get("email") or "").strip()
    if "@" not in email or " " in email:
        flash("Enter a valid email address.", "error")
    else:
        suppress(email, "manual")
        flash(f"Blocked {email}.", "success")
    return redirect(url_for("admin.suppressions"))


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
    solves = sorted(
        team.solves,
        key=lambda s: s.puzzle.order_index if s.puzzle else 0,
    )
    return render_template(
        "admin/team_detail.html",
        team=team,
        other_teams=Team.query.filter(Team.id != team.id).order_by(Team.name.asc()).all(),
        current=current_puzzle(team),
        solved=len(team.solves),
        total=len(published_puzzles()),
        solves=solves,
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


@bp.route("/teams/<int:team_id>/puzzles/<int:puzzle_id>/reset", methods=["POST"])
@login_required
@admin_required
def team_reset_solve(team_id: int, puzzle_id: int):
    """Un-solve one puzzle for a team by deleting its Solve row.

    The submission/audit history is intentionally kept. Because the current
    puzzle is the lowest published puzzle a team hasn't solved, resetting an
    earlier puzzle re-opens it as the team's current puzzle.
    """
    team = db.session.get(Team, team_id)
    if team is None:
        abort(404)
    solve = Solve.query.filter_by(team_id=team_id, puzzle_id=puzzle_id).first()
    if solve is None:
        flash("That puzzle isn't marked solved for this team.", "error")
    else:
        puzzle = db.session.get(Puzzle, puzzle_id)
        label = (
            f"#{puzzle.order_index} — {puzzle.title}" if puzzle else f"puzzle {puzzle_id}"
        )
        db.session.delete(solve)
        db.session.commit()
        flash(
            f"Reset {team.name}'s progress on {label}. Their attempt history is kept.",
            "success",
        )
    return redirect(url_for("admin.team_detail", team_id=team_id))


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


@bp.route("/members/<int:user_id>/delete", methods=["POST"])
@login_required
@admin_required
def member_delete(user_id: int):
    user = db.session.get(User, user_id)
    if user is None:
        abort(404)
    # Never delete the only remaining admin (would lock everyone out of /admin).
    if user.is_admin and User.query.filter_by(is_admin=True).count() <= 1:
        flash("Can't delete the last admin.", "error")
        return _redirect_after_member_action()

    label = _member_label(user)
    # Keep the team's progress: detach this player from their solves rather than
    # deleting them (solved_by_id is nullable).
    Solve.query.filter_by(solved_by_id=user.id).update(
        {"solved_by_id": None}, synchronize_session=False
    )
    # Teams they created stay; just clear the creator reference.
    Team.query.filter_by(created_by_id=user.id).update(
        {"created_by_id": None}, synchronize_session=False
    )
    # Submission.user_id is NOT NULL, so this player's attempts are removed.
    Submission.query.filter_by(user_id=user.id).delete(synchronize_session=False)
    db.session.delete(user)
    db.session.commit()
    flash(f"Deleted {label}.", "success")
    return _redirect_after_member_action()
