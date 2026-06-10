"""Puzzle media: admin upload/overwrite and per-puzzle access control."""
from io import BytesIO


def _puzzle_ids(app):
    from app.models import Puzzle

    with app.app_context():
        p1 = Puzzle.query.filter_by(order_index=1).first().id
        p2 = Puzzle.query.filter_by(order_index=2).first().id
    return p1, p2


def _upload(client, puzzle_id, filename, content):
    return client.post(
        f"/admin/puzzles/{puzzle_id}/media",
        data={"files": (BytesIO(content), filename)},
        content_type="multipart/form-data",
    )


def test_non_admin_cannot_upload(client, app, login, two_puzzles):
    p1, _ = _puzzle_ids(app)
    login("admin@example.com")  # first user -> admin
    client.post("/logout")
    login("player@example.com")  # second user -> NOT admin
    assert _upload(client, p1, "x.png", b"data").status_code == 403


def test_media_gated_like_its_puzzle(client, app, login, two_puzzles):
    p1, p2 = _puzzle_ids(app)

    # Admin (first user) uploads an image to each puzzle.
    login("admin@example.com")
    _upload(client, p1, "a.png", b"PNGDATA1")
    _upload(client, p2, "b.png", b"PNGDATA2")

    # A non-admin player on a team is on puzzle 1 (current); puzzle 2 is locked.
    client.post("/logout")
    login("player@example.com")
    client.post("/team/create", data={"name": "Crew"})

    ok = client.get(f"/media/puzzle/{p1}/a.png")
    assert ok.status_code == 200
    assert ok.data == b"PNGDATA1"

    locked = client.get(f"/media/puzzle/{p2}/b.png")
    assert locked.status_code == 403


def test_admin_may_preview_locked_media(client, app, login, two_puzzles):
    _p1, p2 = _puzzle_ids(app)
    login("admin@example.com")
    _upload(client, p2, "b.png", b"PNGDATA2")
    # Admin bypasses progression so they can preview while authoring.
    assert client.get(f"/media/puzzle/{p2}/b.png").status_code == 200


def test_same_name_overwrites(client, app, login, two_puzzles):
    from app.media import list_puzzle_media

    p1, _ = _puzzle_ids(app)
    login("admin@example.com")
    _upload(client, p1, "pic.png", b"FIRST")
    _upload(client, p1, "pic.png", b"SECOND")

    with app.app_context():
        assert list_puzzle_media(p1) == ["pic.png"]  # one file, not two

    # Admin can fetch; content is the overwritten version.
    resp = client.get(f"/media/puzzle/{p1}/pic.png")
    assert resp.status_code == 200
    assert resp.data == b"SECOND"


def test_disallowed_extension_rejected(client, app, login, two_puzzles):
    from app.media import list_puzzle_media

    p1, _ = _puzzle_ids(app)
    login("admin@example.com")
    _upload(client, p1, "evil.exe", b"nope")
    with app.app_context():
        assert list_puzzle_media(p1) == []


def test_delete_removes_file(client, app, login, two_puzzles):
    from app.media import list_puzzle_media

    p1, _ = _puzzle_ids(app)
    login("admin@example.com")
    _upload(client, p1, "a.png", b"data")
    client.post(
        f"/admin/puzzles/{p1}/media/delete",
        data={"filename": "a.png"},
    )
    with app.app_context():
        assert list_puzzle_media(p1) == []
