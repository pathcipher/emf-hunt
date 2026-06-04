"""Application factory."""
from __future__ import annotations

# Load .env before config is imported so os.environ is populated.
from dotenv import load_dotenv

load_dotenv()

import logging

from flask import Flask, render_template

from config import Config
from .extensions import csrf, db, limiter, login_manager


def create_app(config_object: type = Config) -> Flask:
    app = Flask(__name__)
    app.config.from_object(config_object)

    logging.basicConfig(level=logging.INFO)

    db.init_app(app)
    csrf.init_app(app)
    limiter.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = "auth.login"
    login_manager.login_message = "Please log in to continue."
    login_manager.login_message_category = "info"

    from .models import User

    @login_manager.user_loader
    def load_user(user_id: str):
        return db.session.get(User, int(user_id))

    from .admin.routes import bp as admin_bp
    from .auth.routes import bp as auth_bp
    from .puzzles.routes import bp as puzzles_bp
    from .teams.routes import bp as teams_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(teams_bp)
    app.register_blueprint(puzzles_bp)
    app.register_blueprint(admin_bp)

    @app.get("/healthz")
    def healthz():
        # Liveness probe for Docker / load balancers — no auth, no DB.
        return "ok", 200

    _register_security_headers(app)
    _register_error_handlers(app)
    _register_cli(app)

    return app


def _register_security_headers(app: Flask) -> None:
    @app.after_request
    def set_security_headers(resp):
        # Player-supplied content is always escaped by Jinja; puzzle HTML/JS is
        # trusted admin content. CSP allows inline scripts (puzzles run inline JS)
        # while still blocking plugins, framing, and base-tag hijacking.
        resp.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline'; "
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data:; "
            "object-src 'none'; "
            "base-uri 'self'; "
            "frame-ancestors 'self'",
        )
        # Let puzzles read GPS (requires HTTPS / secure context in the browser).
        resp.headers.setdefault("Permissions-Policy", "geolocation=(self)")
        resp.headers.setdefault("X-Content-Type-Options", "nosniff")
        resp.headers.setdefault("Referrer-Policy", "same-origin")
        return resp


def _register_error_handlers(app: Flask) -> None:
    @app.errorhandler(403)
    def forbidden(_e):
        return (
            render_template(
                "error.html",
                code=403,
                message="That area is locked — solve the current puzzle first.",
            ),
            403,
        )

    @app.errorhandler(404)
    def not_found(_e):
        return (
            render_template(
                "error.html", code=404, message="Lost in space — page not found."
            ),
            404,
        )


def _register_cli(app: Flask) -> None:
    from .models import Puzzle

    @app.cli.command("init-db")
    def init_db():
        """Create all database tables."""
        db.create_all()
        print("Database tables created.")

    @app.cli.command("seed-demo")
    def seed_demo():
        """Insert a few clearly-fake demo puzzles (skips any that already exist)."""
        demos = [
            {
                "order_index": 1,
                "title": "Welcome, Traveller",
                "content_html": (
                    "<p>Your hunt begins among the stars. This is a demo puzzle — "
                    "the answer is simply <strong>hello</strong>.</p>"
                ),
                "answer": "hello",
            },
            {
                "order_index": 2,
                "title": "Stellar Cipher",
                "content_html": (
                    "<p>Three stars in a row mark the hunter's belt. Name the "
                    "constellation. (Demo answer: <strong>orion</strong>.)</p>"
                ),
                "answer": "orion",
            },
            {
                "order_index": 3,
                "title": "Ground Control",
                "content_html": (
                    "<p>This puzzle runs JavaScript to read your GPS — proof that "
                    "puzzle pages can use the Geolocation API.</p>"
                    '<button type="button" id="loc-btn">Show my coordinates</button>'
                    '<p id="loc-out" style="margin-top:1rem"></p>'
                    "<script>"
                    "document.getElementById('loc-btn').addEventListener('click',function(){"
                    "var out=document.getElementById('loc-out');"
                    "if(!navigator.geolocation){out.textContent='No geolocation support.';return;}"
                    "out.textContent='Locating\\u2026';"
                    "navigator.geolocation.getCurrentPosition("
                    "function(p){out.textContent='Lat '+p.coords.latitude.toFixed(4)+', Lon '+p.coords.longitude.toFixed(4);},"
                    "function(){out.textContent='Permission denied or unavailable.';});"
                    "});"
                    "</script>"
                    "<p>(Demo answer: <strong>apollo</strong>.)</p>"
                ),
                "answer": "apollo",
            },
        ]
        added = 0
        for data in demos:
            exists = Puzzle.query.filter_by(order_index=data["order_index"]).first()
            if exists:
                continue
            db.session.add(Puzzle(is_published=True, **data))
            added += 1
        db.session.commit()
        print(f"Seeded {added} demo puzzle(s).")
