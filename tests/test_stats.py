"""Admin solve stats: Mission Control dashboard + per-puzzle list figures."""
import re


def _seed(app):
    """3 teams: A guessed only; B solved both published puzzles (100%); C solved P1."""
    from app.extensions import db
    from app.models import Puzzle, Solve, Submission, Team, User

    with app.app_context():
        p1 = Puzzle(order_index=1, title="P1", content_html="x", answer="a", is_published=True)
        p2 = Puzzle(order_index=2, title="P2", content_html="x", answer="b", is_published=True)
        a, b, c = Team(name="A", join_code="AAA111"), Team(name="B", join_code="BBB111"), Team(name="C", join_code="CCC111")
        db.session.add_all([p1, p2, a, b, c])
        db.session.commit()

        ua = User(email="a@x.com", team_id=a.id)
        ub = User(email="b@x.com", team_id=b.id)
        uc = User(email="c@x.com", team_id=c.id)
        db.session.add_all([ua, ub, uc])
        db.session.commit()

        def sub(team, user, puzzle, ok):
            db.session.add(Submission(team_id=team.id, user_id=user.id, puzzle_id=puzzle.id, text="z", is_correct=ok))

        def solve(team, user, puzzle):
            db.session.add(Solve(team_id=team.id, puzzle_id=puzzle.id, solved_by_id=user.id))

        sub(a, ua, p1, False)  # A: guessed P1, no solve
        sub(b, ub, p1, True); solve(b, ub, p1)
        sub(b, ub, p2, True); solve(b, ub, p2)  # B: 100%
        sub(c, uc, p1, True); solve(c, uc, p1)  # C: solved P1 only
        db.session.commit()


def _stat(html, label):
    m = re.search(r'stat-num">([^<]+)</span>\s*<span class="stat-label">' + re.escape(label), html)
    return m.group(1).strip() if m else None


def test_dashboard_solve_stats(client, app, login):
    login("boss@example.com")  # admin (no team)
    _seed(app)
    html = client.get("/admin/").get_data(as_text=True)
    assert _stat(html, "teams with a guess") == "3"
    assert _stat(html, "teams with a solve") == "2"
    assert _stat(html, "teams 100% solved") == "1"


def test_puzzle_list_stats(client, app, login):
    login("boss@example.com")
    _seed(app)
    body = client.get("/admin/puzzles").get_data(as_text=True)
    # P1: all 3 teams guessed, 2 of 3 solved -> 67%
    assert "3 teams started" in body
    assert "67% solved" in body
    # P2: only B guessed/solved -> 1 team started, 33%
    assert "1 team started" in body
    assert "33% solved" in body


def test_stats_zero_safe(client, app, login):
    login("boss@example.com")  # admin, no teams/puzzles seeded
    assert client.get("/admin/").status_code == 200
    assert client.get("/admin/puzzles").status_code == 200
