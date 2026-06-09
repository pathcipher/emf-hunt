"""Strict, server-enforced team progression."""


def _make_team(client, name="Rockets"):
    client.post("/team/create", data={"name": name})


def test_future_puzzle_is_locked(client, login, two_puzzles):
    login("p1@example.com")
    _make_team(client)
    assert client.get("/puzzle/2").status_code == 403


def test_wrong_answer_does_not_advance(client, app, login, two_puzzles):
    login("p1@example.com")
    _make_team(client)
    client.post("/puzzle/1/submit", data={"answer": "not-it"})

    with app.app_context():
        from app.models import Solve

        assert Solve.query.count() == 0
    assert client.get("/puzzle/2").status_code == 403  # still locked


def test_correct_answer_advances(client, app, login, two_puzzles):
    login("p1@example.com")
    _make_team(client)

    # Note the messy case/whitespace — normalization should still match.
    client.post("/puzzle/1/submit", data={"answer": "  ALPHA "})

    with app.app_context():
        from app.models import Solve

        assert Solve.query.count() == 1

    assert client.get("/puzzle/2").status_code == 200  # now unlocked
    idx = client.get("/", follow_redirects=False)
    assert idx.status_code == 302
    assert idx.headers["Location"].endswith("/puzzle/2")


def test_cannot_submit_to_non_current_puzzle(client, login, two_puzzles):
    login("p1@example.com")
    _make_team(client)
    # Puzzle 2 is not the current puzzle yet — submitting must be rejected.
    assert client.post("/puzzle/2/submit", data={"answer": "beta"}).status_code == 403


def test_multiple_answers_all_accepted(client, app, login):
    """Test that puzzles with multiple answers accept any of them."""
    from app.extensions import db
    from app.models import Puzzle, Submission

    login("p1@example.com")
    client.post("/team/create", data={"name": "Test"})

    with app.app_context():
        # Clear and add a multi-answer puzzle
        Puzzle.query.delete()
        db.session.add(
            Puzzle(
                order_index=1,
                title="Multi",
                content_html="<p>multi</p>",
                answer='["hello", "hi", "hey"]',
                is_published=True,
            )
        )
        db.session.commit()

    # Each answer should be accepted
    for ans in ["hello", "hi", "hey"]:
        client.post("/puzzle/1/submit", data={"answer": ans})
        with app.app_context():
            last = Submission.query.order_by(Submission.id.desc()).first()
            assert last.is_correct, f"Answer '{ans}' should be correct"
