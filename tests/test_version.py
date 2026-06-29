"""The semantic version is exposed and shown in the footer."""
import re


def test_version_is_semver():
    from app.__version__ import __version__

    assert re.match(r"^\d+\.\d+\.\d+", __version__), __version__


def test_version_shown_in_footer(client):
    from app.__version__ import __version__

    body = client.get("/login").get_data(as_text=True)  # public page, has the footer
    assert f"v{__version__}" in body


def test_app_version_env_override(client, monkeypatch):
    monkeypatch.setenv("APP_VERSION", "9.9.9-rc1")
    body = client.get("/login").get_data(as_text=True)
    assert "v9.9.9-rc1" in body


def test_build_revision_shown_when_set(client, monkeypatch):
    monkeypatch.setenv("APP_REVISION", "abcdef1234567890")
    body = client.get("/login").get_data(as_text=True)
    assert "abcdef1" in body  # short SHA
    assert "abcdef1234567890" not in body  # truncated to 7
