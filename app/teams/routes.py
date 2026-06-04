"""Team create / join / view. Progression is shared across a team."""
from __future__ import annotations

from flask import Blueprint, flash, redirect, render_template, url_for
from flask_login import current_user, login_required

from ..extensions import db
from ..models import Team, generate_join_code
from .forms import CreateTeamForm, JoinTeamForm

bp = Blueprint("teams", __name__)


@bp.route("/team")
@login_required
def setup():
    if current_user.team_id is not None:
        return redirect(url_for("teams.view"))
    return render_template(
        "teams/setup.html", create_form=CreateTeamForm(), join_form=JoinTeamForm()
    )


@bp.route("/team/create", methods=["POST"])
@login_required
def create():
    if current_user.team_id is not None:
        return redirect(url_for("teams.view"))

    form = CreateTeamForm()
    if form.validate_on_submit():
        name = form.name.data.strip()
        if Team.query.filter_by(name=name).first():
            flash("That team name is taken — pick another.", "error")
        else:
            code = generate_join_code()
            while Team.query.filter_by(join_code=code).first():
                code = generate_join_code()
            team = Team(name=name, join_code=code, created_by=current_user)
            db.session.add(team)
            db.session.flush()
            current_user.team_id = team.id
            db.session.commit()
            flash("Team created! Share your join code with teammates.", "success")
            return redirect(url_for("teams.view"))

    return render_template(
        "teams/setup.html", create_form=form, join_form=JoinTeamForm()
    )


@bp.route("/team/join", methods=["POST"])
@login_required
def join():
    if current_user.team_id is not None:
        return redirect(url_for("teams.view"))

    form = JoinTeamForm()
    if form.validate_on_submit():
        code = form.join_code.data.strip().upper()
        team = Team.query.filter_by(join_code=code).first()
        if team is None:
            flash("No team found with that code.", "error")
        else:
            current_user.team_id = team.id
            db.session.commit()
            flash(f"You've joined {team.name}!", "success")
            return redirect(url_for("teams.view"))

    return render_template(
        "teams/setup.html", create_form=CreateTeamForm(), join_form=form
    )


@bp.route("/team/me")
@login_required
def view():
    if current_user.team_id is None:
        return redirect(url_for("teams.setup"))
    team = db.session.get(Team, current_user.team_id)
    return render_template("teams/view.html", team=team)
