"""Admin live-submissions feed: gating, filters, cursor, and escaping."""


def _seed(app):
    """Three submissions from one team/player on one puzzle (1 correct, 2 wrong)."""
    from app.extensions import db
    from app.models import Puzzle, Submission, Team, User

    with app.app_context():
        user = User(email="solver@example.com")
        team = Team(name="Nebula", join_code="NEB123")
        puzzle = Puzzle(
            order_index=1, title="P1", content_html="<p>x</p>", answer="z", is_published=True
        )
        db.session.add_all([user, team, puzzle])
        db.session.commit()
        db.session.add_all(
            [
                Submission(team_id=team.id, user_id=user.id, puzzle_id=puzzle.id,
                           text="first-wrong", is_correct=False),
                Submission(team_id=team.id, user_id=user.id, puzzle_id=puzzle.id,
                           text="right-one", is_correct=True),
                Submission(team_id=team.id, user_id=user.id, puzzle_id=puzzle.id,
                           text="<b>xss</b>", is_correct=False),
            ]
        )
        db.session.commit()
        return {"team": team.id, "puzzle": puzzle.id}


def test_submissions_requires_admin(client, login):
    login("boss@example.com")  # first user = admin
    client.post("/logout")
    login("npc@example.com")  # not admin
    assert client.get("/admin/submissions").status_code == 403
    assert client.get("/admin/submissions.json").status_code == 403


def test_submissions_page_escapes_untrusted_text(client, app, login):
    login("boss@example.com")
    _seed(app)
    r = client.get("/admin/submissions")
    assert r.status_code == 200
    assert b"<b>xss</b>" not in r.data
    assert b"&lt;b&gt;xss&lt;/b&gt;" in r.data


def test_feed_returns_all_and_serializes(client, app, login):
    login("boss@example.com")
    _seed(app)
    data = client.get("/admin/submissions.json?after=0").get_json()
    assert len(data["submissions"]) == 3
    row = data["submissions"][0]
    assert {"id", "time", "team", "player", "puzzle", "text", "correct"} <= set(row)
    assert row["team"] == "Nebula"


def test_feed_result_filter(client, app, login):
    login("boss@example.com")
    _seed(app)
    correct = client.get("/admin/submissions.json?after=0&result=correct").get_json()
    assert len(correct["submissions"]) == 1
    assert correct["submissions"][0]["correct"] is True

    wrong = client.get("/admin/submissions.json?after=0&result=wrong").get_json()
    assert len(wrong["submissions"]) == 2


def test_feed_team_filter(client, app, login):
    login("boss@example.com")
    ids = _seed(app)
    matched = client.get(f"/admin/submissions.json?after=0&team={ids['team']}").get_json()
    assert len(matched["submissions"]) == 3
    missing = client.get(f"/admin/submissions.json?after=0&team={ids['team'] + 999}").get_json()
    assert missing["submissions"] == []


def test_feed_cursor_only_returns_newer(client, app, login):
    login("boss@example.com")
    _seed(app)
    first = client.get("/admin/submissions.json?after=0").get_json()
    cursor = first["cursor"]
    # Nothing newer than the latest id.
    assert client.get(f"/admin/submissions.json?after={cursor}").get_json()["submissions"] == []


def test_feed_snapshot_without_after_returns_latest(client, app, login):
    """No ?after => snapshot of newest matching rows (oldest-first for prepending)."""
    login("boss@example.com")
    _seed(app)
    data = client.get("/admin/submissions.json").get_json()
    texts = [s["text"] for s in data["submissions"]]
    assert texts == ["first-wrong", "right-one", "<b>xss</b>"]  # oldest -> newest
    assert data["cursor"] == data["submissions"][-1]["id"]


def test_snapshot_respects_result_filter(client, app, login):
    login("boss@example.com")
    _seed(app)
    data = client.get("/admin/submissions.json?result=wrong").get_json()
    assert [s["text"] for s in data["submissions"]] == ["first-wrong", "<b>xss</b>"]


def test_html_page_filters_server_side(client, app, login):
    """The no-JS path: the rendered table itself respects the filter params."""
    login("boss@example.com")
    _seed(app)
    r = client.get("/admin/submissions?result=correct")
    assert b"right-one" in r.data
    assert b"first-wrong" not in r.data
