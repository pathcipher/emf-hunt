"""Application factory."""
from __future__ import annotations

# Load .env before config is imported so os.environ is populated.
from dotenv import load_dotenv

load_dotenv()

import logging
import os

from flask import Flask, render_template

from config import Config
from .__version__ import __version__
from .extensions import csrf, db, limiter, login_manager


def _reconcile_schema() -> None:
    """Reconcile the database schema on startup.

    Creates missing tables and adds missing columns to existing tables.
    This ensures the schema is always up-to-date without requiring manual migrations.
    """
    logger = logging.getLogger("emf_hunt.schema")

    # Create all tables defined in models (idempotent).
    db.create_all()
    logger.info("Database schema created/verified.")

    # Check for missing columns and add them if needed.
    from sqlalchemy import inspect, text

    inspector = inspect(db.engine)
    for table in db.metadata.tables.values():
        table_name = table.name
        if not inspector.has_table(table_name):
            continue

        existing_cols = {col["name"] for col in inspector.get_columns(table_name)}
        model_cols = {col.name for col in table.columns}
        missing = model_cols - existing_cols

        for col_name in missing:
            col = table.columns[col_name]
            # Build ALTER TABLE statement
            col_type = str(col.type)
            nullable = "NOT NULL" if not col.nullable else ""
            default = f"DEFAULT {col.default.arg}" if col.default else ""
            alter_stmt = f"ALTER TABLE {table_name} ADD COLUMN {col_name} {col_type} {nullable} {default}".strip()
            try:
                db.session.execute(text(alter_stmt))
                logger.info(f"Added missing column {table_name}.{col_name}")
            except Exception as e:
                logger.warning(f"Failed to add column {table_name}.{col_name}: {e}")
    db.session.commit()


def create_app(config_object: type = Config) -> Flask:
    app = Flask(__name__)
    app.config.from_object(config_object)

    logging.basicConfig(level=logging.INFO)

    # Ensure the puzzle-media directory exists (mounted volume in Docker).
    os.makedirs(app.config["MEDIA_ROOT"], exist_ok=True)

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
    from .branding import bp as branding_bp
    from .puzzles.routes import bp as puzzles_bp
    from .teams.routes import bp as teams_bp
    from .webhooks import bp as webhooks_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(teams_bp)
    app.register_blueprint(puzzles_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(branding_bp)
    app.register_blueprint(webhooks_bp)
    # SNS posts without a CSRF token; the route's trust comes from SNS signature
    # verification instead (see app/webhooks.py).
    csrf.exempt(webhooks_bp)

    @app.get("/healthz")
    def healthz():
        # Liveness probe for Docker / load balancers — no auth, no DB.
        return "ok", 200

    @app.context_processor
    def inject_template_globals():
        # Make site_name and contact info available in every template.
        try:
            from .progression import parallel_mode
            pmode = parallel_mode()
        except Exception:  # never let this break a render (e.g. DB hiccup)
            pmode = bool(app.config.get("PARALLEL_MODE", False))
        return {
            "site_name": app.config["SITE_NAME"],
            "contact_name": app.config["CONTACT_NAME"],
            "contact_email": app.config["CONTACT_EMAIL"],
            "contact_phone": app.config["CONTACT_PHONE"],
            "parallel_mode": pmode,
            # APP_VERSION lets a build stamp a more specific string; otherwise show
            # the packaged semantic version. APP_REVISION (commit SHA, baked in at
            # build time) changes every deploy so you can confirm what's live.
            "app_version": os.environ.get("APP_VERSION") or __version__,
            "app_revision": (os.environ.get("APP_REVISION") or "")[:7],
        }

    _register_security_headers(app)
    _register_error_handlers(app)
    _register_cli(app)

    # Reconcile database schema on startup.
    with app.app_context():
        _reconcile_schema()

    return app


def _register_security_headers(app: Flask) -> None:
    # When Turnstile is enabled the login page loads Cloudflare's script and an
    # iframe, so the CSP must allow that origin (only then — kept tight otherwise).
    turnstile = "https://challenges.cloudflare.com"
    extra_connect = " ".join(
        o for o in app.config.get("EXTRA_CONNECT_SRC", "").split() if o
    )
    connect_origins = " ".join(filter(None, [
        "'self'",
        turnstile if app.config.get("TURNSTILE_SITE_KEY") else "",
        extra_connect,
    ]))
    connect_src = f"connect-src {connect_origins}; "

    if app.config.get("TURNSTILE_SITE_KEY"):
        script_src = f"script-src 'self' 'unsafe-inline' {turnstile}; "
        frame_src = f"frame-src {turnstile}; "
    else:
        script_src = "script-src 'self' 'unsafe-inline'; "
        frame_src = ""

    jsdelivr = "https://cdn.jsdelivr.net"
    csp = (
        "default-src 'self'; "
        + script_src.rstrip("; ") + f" {jsdelivr}; "
        + f"style-src 'self' 'unsafe-inline' {jsdelivr}; "
        + "img-src 'self' data:; "
        + connect_src
        + frame_src
        + "object-src 'none'; "
        + "base-uri 'self'; "
        + "frame-ancestors 'self'"
    )

    @app.after_request
    def set_security_headers(resp):
        # Player-supplied content is always escaped by Jinja; puzzle HTML/JS is
        # trusted admin content. CSP allows inline scripts (puzzles run inline JS)
        # while still blocking plugins, framing, and base-tag hijacking.
        resp.headers.setdefault("Content-Security-Policy", csp)
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
