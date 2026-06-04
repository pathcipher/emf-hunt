"""Admin gating + the trust boundary: puzzle HTML trusted, player input escaped."""


def test_non_admin_blocked_from_admin(client, login):
    login("boss@example.com")  # first user = admin
    client.post("/logout")
    login("npc@example.com")  # second user = not admin
    assert client.get("/admin/").status_code == 403


def test_admin_can_reach_dashboard(client, login):
    login("boss@example.com")
    assert client.get("/admin/").status_code == 200


def test_admin_puzzle_html_renders_intact(client, login):
    """Trusted admin content (incl. <script>/geolocation) is rendered unescaped."""
    login("boss@example.com")
    payload = '<script id="geo">navigator.geolocation.getCurrentPosition</script><p>hi</p>'
    r = client.post(
        "/admin/puzzles/new",
        data={
            "order_index": "1",
            "title": "JS Puzzle",
            "content_html": payload,
            "answer": "x",
            "is_published": "y",
        },
        follow_redirects=True,
    )
    assert r.status_code == 200

    client.post("/team/create", data={"name": "Admins"})  # need a team to view
    page = client.get("/puzzle/1")
    assert page.status_code == 200
    assert payload.encode() in page.data  # intact, not stripped or escaped


def test_player_team_name_is_escaped(client, login):
    """Untrusted player input (team name) is HTML-escaped when echoed back."""
    login("boss@example.com")
    client.post("/team/create", data={"name": "<script>alert(1)</script>"})
    page = client.get("/team/me")
    assert page.status_code == 200
    assert b"<script>alert(1)</script>" not in page.data
    assert b"&lt;script&gt;alert(1)&lt;/script&gt;" in page.data
