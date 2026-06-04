"""Magic-link auth: first-user-admin, single-use tokens, enumeration safety."""


def test_index_requires_login(client):
    r = client.get("/", follow_redirects=False)
    assert r.status_code == 302
    assert "/login" in r.headers["Location"]


def test_first_user_becomes_admin(app, login):
    login("boss@example.com")
    with app.app_context():
        from app.models import User

        user = User.query.filter_by(email="boss@example.com").first()
        assert user is not None
        assert user.is_admin is True


def test_second_user_is_not_admin(client, app, login):
    login("boss@example.com")
    client.post("/logout")
    login("npc@example.com")
    with app.app_context():
        from app.models import User

        assert User.query.filter_by(email="npc@example.com").first().is_admin is False


def test_magic_link_is_single_use(client, magic):
    client.post("/login", data={"email": "once@example.com"})
    token = magic["token"]

    first = client.get(f"/auth/verify/{token}", follow_redirects=False)
    assert first.status_code == 302  # logged in -> redirected onward
    client.post("/logout")

    second = client.get(f"/auth/verify/{token}", follow_redirects=False)
    assert second.status_code == 302
    assert "/login" in second.headers["Location"]  # token already burned


def test_login_is_enumeration_safe(client, magic):
    r = client.post("/login", data={"email": "stranger@example.com"})
    assert r.status_code == 200
    assert b"Check your email" in r.data
