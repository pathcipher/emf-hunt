"""Magic-link authentication: request a link, verify it, log out."""
from __future__ import annotations

from urllib.parse import urljoin

from flask import (
    Blueprint,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    url_for,
)
from flask_limiter.util import get_remote_address
from flask_login import current_user, login_required, login_user, logout_user

from ..captcha import verify_turnstile
from ..email import send_magic_link
from ..extensions import db, limiter
from ..models import User
from ..security import consume_login_token, create_login_token
from ..suppression import is_suppressed
from .forms import LoginForm

bp = Blueprint("auth", __name__)


def _login_rate_key() -> str:
    """Rate-limit magic-link requests *per email*, not per IP.

    EMF camp wifi is heavily NAT'd, so IP-based limits would punish whole groups.
    Keying on the target email instead blocks email-bombing without that collateral.
    """
    email = (request.form.get("email") or "").strip().lower()
    return email or get_remote_address()


@bp.route("/login", methods=["GET", "POST"])
@limiter.limit("6 per hour", key_func=_login_rate_key, methods=["POST"])
@limiter.limit("1 per 10 seconds", key_func=_login_rate_key, methods=["POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("puzzles.index"))

    form = LoginForm()
    if form.validate_on_submit():
        if not verify_turnstile(request.form.get("cf-turnstile-response")):
            flash("Please complete the verification and try again.", "error")
            return _render_login(form)

        email = form.email.data.strip().lower()
        # Don't email addresses that complained or hard-bounced (protects SES
        # reputation), but respond identically so suppression isn't observable.
        if not is_suppressed(email):
            raw = create_login_token(email)
            link = urljoin(
                current_app.config["BASE_URL"], url_for("auth.verify", token=raw)
            )
            send_magic_link(email, link)
        # Always the same response — never reveal whether an account exists.
        return render_template("auth/check_email.html", email=email)

    return _render_login(form)


def _render_login(form: LoginForm):
    return render_template(
        "auth/login.html",
        form=form,
        turnstile_site_key=current_app.config["TURNSTILE_SITE_KEY"],
    )


@bp.route("/auth/verify/<token>")
def verify(token: str):
    email = consume_login_token(token)
    if email is None:
        flash("That login link is invalid or has expired — request a new one.", "error")
        return redirect(url_for("auth.login"))

    user = User.query.filter_by(email=email).first()
    if user is None:
        # The very first user to log in becomes an admin.
        is_first_user = User.query.count() == 0
        user = User(email=email, is_admin=is_first_user)
        db.session.add(user)
        db.session.commit()

    login_user(user, remember=True)

    if user.team_id is None:
        return redirect(url_for("teams.setup"))
    return redirect(url_for("puzzles.index"))


@bp.route("/logout", methods=["POST"])
@login_required
def logout():
    logout_user()
    flash("You've been logged out.", "info")
    return redirect(url_for("auth.login"))
