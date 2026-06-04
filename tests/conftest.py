import os
import tempfile

import pytest

from app import create_app
from app.extensions import db as _db
from config import Config


class TestConfig(Config):
    TESTING = True
    WTF_CSRF_ENABLED = False  # let tests POST forms without a token
    RATELIMIT_ENABLED = False  # don't 429 during tests
    SECRET_KEY = "test-secret-key"
    EMAIL_BACKEND = "console"
    BASE_URL = "http://localhost"


@pytest.fixture
def app():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    TestConfig.SQLALCHEMY_DATABASE_URI = f"sqlite:///{path}"

    application = create_app(TestConfig)
    with application.app_context():
        _db.create_all()

    yield application

    with application.app_context():
        _db.session.remove()
        _db.drop_all()
    os.unlink(path)


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def magic(client, monkeypatch):
    """Capture the magic link instead of 'sending' it, so tests can follow it."""
    import app.auth.routes as auth_routes

    box = {}

    def fake_send(email, link):
        box["email"] = email
        box["link"] = link
        box["token"] = link.rsplit("/", 1)[-1]

    monkeypatch.setattr(auth_routes, "send_magic_link", fake_send)
    return box


@pytest.fixture
def login(client, magic):
    """Log the test client in as `email`, creating the user via the magic-link flow."""

    def do(email="player@example.com"):
        client.post("/login", data={"email": email})
        return client.get(f"/auth/verify/{magic['token']}")

    return do


@pytest.fixture
def two_puzzles(app):
    """Two published puzzles, answers 'alpha' (order 1) and 'beta' (order 2)."""
    from app.models import Puzzle

    with app.app_context():
        _db.session.add_all(
            [
                Puzzle(
                    order_index=1,
                    title="One",
                    content_html="<p>one</p>",
                    answer="alpha",
                    is_published=True,
                ),
                Puzzle(
                    order_index=2,
                    title="Two",
                    content_html="<p>two</p>",
                    answer="beta",
                    is_published=True,
                ),
            ]
        )
        _db.session.commit()
