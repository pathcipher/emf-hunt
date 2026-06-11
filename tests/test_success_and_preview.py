"""Customisable success page + admin puzzle preview."""


def _add_puzzle(app, *, order=1, answer="x", published=True, content="<p>body</p>", title="P"):
    from app.extensions import db
    from app.models import Puzzle

    with app.app_context():
        p = Puzzle(
            order_index=order,
            title=title,
            content_html=content,
            answer=answer,
            is_published=published,
        )
        db.session.add(p)
        db.session.commit()
        return p.id


# --- Success page ----------------------------------------------------------

def test_default_success_page_when_unset(client, app, login):
    _add_puzzle(app, order=1, answer="x")
    login("boss@example.com")  # admin + player
    client.post("/team/create", data={"name": "Crew"})
    client.post("/puzzle/1/submit", data={"answer": "x"})  # solves the only puzzle

    page = client.get("/")
    assert page.status_code == 200
    assert b"You did it" in page.data  # built-in default


def test_custom_success_page_with_escaped_team_name(client, app, login):
    _add_puzzle(app, order=1, answer="x")
    login("boss@example.com")

    # Admin sets a custom success page using the {{team_name}} token.
    client.post(
        "/admin/success-page",
        data={"content_html": "<h1>CHAMPIONS: {{team_name}}</h1>"},
    )

    client.post("/team/create", data={"name": "<b>Crew</b>"})  # HTML-y team name
    client.post("/puzzle/1/submit", data={"answer": "x"})

    page = client.get("/")
    body = page.get_data(as_text=True)
    assert "CHAMPIONS:" in body  # custom content shown
    assert "&lt;b&gt;Crew&lt;/b&gt;" in body  # team name escaped, not raw
    assert "<b>Crew</b>" not in body


def test_success_page_editor_requires_admin(client, login):
    login("boss@example.com")
    client.post("/logout")
    login("npc@example.com")
    assert client.get("/admin/success-page").status_code == 403
    assert client.post("/admin/success-page", data={"content_html": "x"}).status_code == 403


# --- Admin puzzle preview --------------------------------------------------

def test_admin_can_preview_unpublished_puzzle(client, app, login):
    pid = _add_puzzle(app, order=1, answer="sesame", published=False, content="<p>OPEN</p>")
    login("boss@example.com")

    r = client.get(f"/admin/puzzles/{pid}/preview")
    assert r.status_code == 200
    body = r.get_data(as_text=True)
    assert "OPEN" in body  # puzzle content rendered
    assert "sesame" in body  # accepted answer shown to admin
    assert "Admin preview" in body  # preview banner


def test_preview_shows_multiple_answers(client, app, login):
    pid = _add_puzzle(app, order=1, answer='["alpha", "beta"]', published=False)
    login("boss@example.com")
    body = client.get(f"/admin/puzzles/{pid}/preview").get_data(as_text=True)
    assert "alpha" in body and "beta" in body


def test_preview_requires_admin(client, app, login):
    pid = _add_puzzle(app, order=1)
    login("boss@example.com")
    client.post("/logout")
    login("npc@example.com")
    assert client.get(f"/admin/puzzles/{pid}/preview").status_code == 403


def test_preview_records_nothing(client, app, login):
    from app.models import Solve, Submission

    pid = _add_puzzle(app, order=1, answer="x", published=False)
    login("boss@example.com")
    client.get(f"/admin/puzzles/{pid}/preview")
    with app.app_context():
        assert Solve.query.count() == 0
        assert Submission.query.count() == 0
