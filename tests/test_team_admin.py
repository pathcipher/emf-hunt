"""Admin team management: gating, member moves, admin toggle, rename, delete."""


def _setup(app):
    """Two teams (Alpha with 2 members, Bravo empty) + a solve & submission on Alpha."""
    from app.extensions import db
    from app.models import Puzzle, Solve, Submission, Team, User

    with app.app_context():
        alpha = Team(name="Alpha", join_code="ALPHA1")
        bravo = Team(name="Bravo", join_code="BRAVO1")
        db.session.add_all([alpha, bravo])
        db.session.commit()

        u1 = User(email="m1@example.com", team_id=alpha.id)
        u2 = User(email="m2@example.com", team_id=alpha.id)
        puzzle = Puzzle(
            order_index=1, title="P", content_html="<p>x</p>", answer="z", is_published=True
        )
        db.session.add_all([u1, u2, puzzle])
        db.session.commit()

        db.session.add(Solve(team_id=alpha.id, puzzle_id=puzzle.id, solved_by_id=u1.id))
        db.session.add(
            Submission(team_id=alpha.id, user_id=u1.id, puzzle_id=puzzle.id, text="z", is_correct=True)
        )
        db.session.commit()
        return {"alpha": alpha.id, "bravo": bravo.id, "u1": u1.id, "u2": u2.id}


def _get(app, model, pk):
    from app.extensions import db

    with app.app_context():
        return db.session.get(model, pk)


def test_team_admin_requires_admin(client, login):
    login("boss@example.com")  # first user = admin
    client.post("/logout")
    login("npc@example.com")  # not admin
    assert client.get("/admin/teams").status_code == 403
    assert client.post("/admin/teams/1/delete").status_code == 403


def test_view_teams_page(client, app, login):
    login("boss@example.com")
    _setup(app)
    r = client.get("/admin/teams")
    assert r.status_code == 200
    assert b"Alpha" in r.data and b"Bravo" in r.data


def test_team_detail_page_renders(client, app, login):
    login("boss@example.com")
    ids = _setup(app)
    r = client.get(f"/admin/teams/{ids['alpha']}")
    assert r.status_code == 200
    assert b"m1@example.com" in r.data  # member listed
    assert b"ALPHA1" in r.data  # join code shown
    assert b"Bravo" in r.data  # other team offered as a move target


def test_move_member_to_another_team(client, app, login):
    login("boss@example.com")
    ids = _setup(app)
    from app.models import User

    client.post(f"/admin/members/{ids['u2']}/move", data={"team_id": ids["bravo"]})
    assert _get(app, User, ids["u2"]).team_id == ids["bravo"]


def test_remove_member_from_team(client, app, login):
    login("boss@example.com")
    ids = _setup(app)
    from app.models import User

    client.post(f"/admin/members/{ids['u1']}/move", data={"team_id": ""})
    assert _get(app, User, ids["u1"]).team_id is None


def test_toggle_admin_with_last_admin_guard(client, app, login):
    login("boss@example.com")
    ids = _setup(app)
    from app.models import User

    with app.app_context():
        from app.extensions import db

        boss_id = db.session.query(User).filter_by(email="boss@example.com").first().id

    # Promote a member.
    client.post(f"/admin/members/{ids['u1']}/toggle-admin", data={})
    assert _get(app, User, ids["u1"]).is_admin is True
    # Demote them again.
    client.post(f"/admin/members/{ids['u1']}/toggle-admin", data={})
    assert _get(app, User, ids["u1"]).is_admin is False
    # Boss is now the sole admin — demoting them must be refused.
    client.post(f"/admin/members/{boss_id}/toggle-admin", data={})
    assert _get(app, User, boss_id).is_admin is True


def test_rename_team(client, app, login):
    login("boss@example.com")
    ids = _setup(app)
    from app.models import Team

    client.post(f"/admin/teams/{ids['alpha']}/rename", data={"name": "Alpha Prime"})
    assert _get(app, Team, ids["alpha"]).name == "Alpha Prime"
    # Renaming to an existing team's name is rejected.
    client.post(f"/admin/teams/{ids['alpha']}/rename", data={"name": "Bravo"})
    assert _get(app, Team, ids["alpha"]).name == "Alpha Prime"


def test_regenerate_join_code(client, app, login):
    login("boss@example.com")
    ids = _setup(app)
    from app.models import Team

    old = _get(app, Team, ids["alpha"]).join_code
    client.post(f"/admin/teams/{ids['alpha']}/regenerate-code", data={})
    assert _get(app, Team, ids["alpha"]).join_code != old


def test_delete_team_cleans_up(client, app, login):
    login("boss@example.com")
    ids = _setup(app)
    from app.models import Solve, Submission, Team, User

    client.post(f"/admin/teams/{ids['alpha']}/delete", data={})

    assert _get(app, Team, ids["alpha"]) is None
    assert _get(app, User, ids["u1"]).team_id is None  # members unassigned, not deleted
    with app.app_context():
        assert Solve.query.filter_by(team_id=ids["alpha"]).count() == 0
        assert Submission.query.filter_by(team_id=ids["alpha"]).count() == 0
