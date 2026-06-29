"""Parallel mode: all published puzzles open at once, filterable by tags."""


def _team(client):
    client.post("/team/create", data={"name": "Crew"})


# --- Puzzle.get_tags parsing ----------------------------------------------

def test_get_tags_parsing(app):
    from app.models import Puzzle

    with app.app_context():
        p = Puzzle(order_index=1, title="t", content_html="x", answer="a", tags="cipher, Easy ,, easy, outdoor")
        # de-duped case-insensitively, blanks dropped, order + original case kept
        assert p.get_tags() == ["cipher", "Easy", "outdoor"]


# --- Progression in parallel mode -----------------------------------------

def test_parallel_unlocks_all_published(client, app, login, two_puzzles):
    app.config["PARALLEL_MODE"] = True
    login("p@example.com")
    _team(client)
    # Puzzle 2 is reachable without solving puzzle 1.
    assert client.get("/puzzle/2").status_code == 200


def test_sequential_still_locks(client, app, login, two_puzzles):
    app.config["PARALLEL_MODE"] = False
    login("p@example.com")
    _team(client)
    assert client.get("/puzzle/2").status_code == 403


def test_parallel_accepts_any_answer(client, app, login, two_puzzles):
    app.config["PARALLEL_MODE"] = True
    login("p@example.com")
    _team(client)
    # Solve puzzle 2 directly (not the sequential "current" puzzle).
    client.post("/puzzle/2/submit", data={"answer": "beta"})
    with app.app_context():
        from app.models import Puzzle, Solve

        p2 = Puzzle.query.filter_by(order_index=2).first()
        assert Solve.query.filter_by(puzzle_id=p2.id).count() == 1


def test_parallel_index_lists_all_published(client, app, login, two_puzzles):
    app.config["PARALLEL_MODE"] = True
    login("p@example.com")
    _team(client)
    body = client.get("/").get_data(as_text=True)
    assert "One" in body and "Two" in body  # both puzzle titles listed


# --- Tag filtering ---------------------------------------------------------

def _seed_tagged(app):
    from app.extensions import db
    from app.models import Puzzle

    with app.app_context():
        db.session.add_all([
            Puzzle(order_index=1, title="Alpha", content_html="x", answer="a", is_published=True, tags="cipher, easy"),
            Puzzle(order_index=2, title="Beta", content_html="x", answer="b", is_published=True, tags="outdoor"),
        ])
        db.session.commit()


def test_tag_filter_narrows_list(client, app, login):
    app.config["PARALLEL_MODE"] = True
    _seed_tagged(app)
    login("p@example.com")
    _team(client)

    full = client.get("/").get_data(as_text=True)
    assert "Alpha" in full and "Beta" in full

    only_outdoor = client.get("/?tag=outdoor").get_data(as_text=True)
    assert "Beta" in only_outdoor
    assert ">Alpha<" not in only_outdoor  # Alpha's title not shown when filtered


def test_tag_chips_rendered(client, app, login):
    app.config["PARALLEL_MODE"] = True
    _seed_tagged(app)
    login("p@example.com")
    _team(client)
    body = client.get("/").get_data(as_text=True)
    for tag in ("cipher", "easy", "outdoor"):
        assert tag in body


# --- Admin runtime toggle --------------------------------------------------

def test_admin_toggle_switches_mode(client, app, login, two_puzzles):
    login("boss@example.com")  # admin + player
    client.post("/team/create", data={"name": "Crew"})

    # Config default is sequential -> puzzle 2 locked.
    assert client.get("/puzzle/2").status_code == 403

    # Toggle parallel ON via the admin UI; setting overrides config.
    client.post("/admin/mode", data={"parallel": "on"})
    assert client.get("/puzzle/2").status_code == 200

    # Toggle back to sequential.
    client.post("/admin/mode", data={"parallel": "off"})
    assert client.get("/puzzle/2").status_code == 403


def test_mode_toggle_requires_admin(client, login):
    login("boss@example.com")
    client.post("/logout")
    login("npc@example.com")  # not admin
    assert client.post("/admin/mode", data={"parallel": "on"}).status_code == 403


def test_dashboard_shows_mode_toggle(client, app, login):
    login("boss@example.com")
    body = client.get("/admin/").get_data(as_text=True)
    assert "Progression mode" in body
    assert "Switch to parallel" in body  # currently sequential


# --- Admin can set tags ----------------------------------------------------

def test_admin_sets_tags(client, app, login):
    login("boss@example.com")
    client.post(
        "/admin/puzzles/new",
        data={"order_index": "1", "title": "T", "content_html": "x", "answer": "y", "tags": "red, blue"},
    )
    with app.app_context():
        from app.models import Puzzle

        p = Puzzle.query.filter_by(order_index=1).first()
        assert p.get_tags() == ["red", "blue"]
