"""Customisable favicon + logo: public serving, admin upload/replace/remove."""
from io import BytesIO


def _upload(client, kind, filename, content):
    return client.post(
        f"/admin/branding/{kind}",
        data={"file": (BytesIO(content), filename)},
        content_type="multipart/form-data",
    )


def test_branding_absent_by_default(client):
    assert client.get("/branding/favicon").status_code == 404
    assert client.get("/branding/logo").status_code == 404
    assert client.get("/favicon.ico").status_code == 404


def test_admin_upload_favicon_and_logo_served_publicly(client, login):
    login("boss@example.com")  # admin
    assert _upload(client, "favicon", "fav.png", b"ICONDATA").status_code == 302
    assert _upload(client, "logo", "logo.svg", b"<svg></svg>").status_code == 302

    fav = client.get("/branding/favicon")
    assert fav.status_code == 200 and fav.data == b"ICONDATA"
    assert client.get("/favicon.ico").status_code == 200

    logo = client.get("/branding/logo")
    assert logo.status_code == 200 and logo.data == b"<svg></svg>"


def test_logo_and_favicon_appear_on_public_login_page(client, login):
    login("boss@example.com")
    _upload(client, "favicon", "fav.png", b"ICONDATA")
    _upload(client, "logo", "logo.png", b"LOGODATA")
    client.post("/logout")  # the login page is public

    body = client.get("/login").get_data(as_text=True)
    assert "/branding/favicon" in body  # favicon <link>
    assert "/branding/logo" in body  # topbar logo <img>
    assert 'class="brand-logo"' in body


def test_upload_replaces_previous_extension(client, app, login):
    from app.branding import branding_dir, get_branding_filename

    login("boss@example.com")
    _upload(client, "logo", "logo.png", b"FIRST")
    _upload(client, "logo", "logo.svg", b"<svg/>")  # different extension

    with app.app_context():
        import os

        files = sorted(os.listdir(branding_dir()))
        assert files == ["logo.svg"]  # old logo.png removed
        assert get_branding_filename("logo") == "logo.svg"

    served = client.get("/branding/logo")
    assert served.data == b"<svg/>"


def test_delete_branding(client, login):
    login("boss@example.com")
    _upload(client, "favicon", "fav.png", b"X")
    assert client.get("/branding/favicon").status_code == 200
    client.post("/admin/branding/favicon/delete", data={})
    assert client.get("/branding/favicon").status_code == 404


def test_disallowed_extension_rejected(client, app, login):
    from app.branding import get_branding_filename

    login("boss@example.com")
    _upload(client, "favicon", "evil.exe", b"nope")
    with app.app_context():
        assert get_branding_filename("favicon") is None


def test_non_admin_cannot_change_branding(client, login):
    login("boss@example.com")
    client.post("/logout")
    login("npc@example.com")  # not admin
    assert _upload(client, "logo", "logo.png", b"x").status_code == 403
    assert client.get("/admin/branding").status_code == 403


def test_unknown_kind_404(client, login):
    login("boss@example.com")
    assert client.post("/admin/branding/banner", data={}).status_code == 404
    assert client.get("/branding/banner").status_code == 404
