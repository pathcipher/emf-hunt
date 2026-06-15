"""Anti-abuse: Turnstile CAPTCHA on login + SES complaint/bounce suppression."""
import json


class _Resp:
    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload


# --- Turnstile -------------------------------------------------------------

def test_verify_turnstile_disabled_when_no_secret(app):
    from app.captcha import verify_turnstile

    with app.app_context():
        assert verify_turnstile(None) is True  # disabled -> passes


def test_verify_turnstile_with_secret(app, monkeypatch):
    from app import captcha

    app.config["TURNSTILE_SECRET_KEY"] = "secret"
    with app.app_context():
        monkeypatch.setattr(captcha.requests, "post", lambda *a, **k: _Resp({"success": True}))
        assert captcha.verify_turnstile("tok") is True
        monkeypatch.setattr(captcha.requests, "post", lambda *a, **k: _Resp({"success": False}))
        assert captcha.verify_turnstile("tok") is False
        assert captcha.verify_turnstile("") is False  # no token


def test_login_blocked_when_captcha_fails(client, app, magic, monkeypatch):
    from app import captcha

    app.config["TURNSTILE_SECRET_KEY"] = "secret"
    monkeypatch.setattr(captcha.requests, "post", lambda *a, **k: _Resp({"success": False}))

    r = client.post("/login", data={"email": "p@example.com"})
    assert r.status_code == 200
    assert "link" not in magic  # no magic link was sent
    assert b"verification" in r.data.lower()


def test_login_succeeds_when_captcha_passes(client, app, magic, monkeypatch):
    from app import captcha

    app.config["TURNSTILE_SECRET_KEY"] = "secret"
    monkeypatch.setattr(captcha.requests, "post", lambda *a, **k: _Resp({"success": True}))

    client.post("/login", data={"email": "p@example.com", "cf-turnstile-response": "tok"})
    assert magic.get("email") == "p@example.com"  # link was sent


# --- Suppression list ------------------------------------------------------

def test_suppressed_address_is_not_emailed(client, app, magic):
    from app.suppression import suppress

    with app.app_context():
        suppress("angry@example.com", "complaint")

    r = client.post("/login", data={"email": "angry@example.com"})
    assert r.status_code == 200
    assert b"Check your email" in r.data  # identical response (no enumeration)
    assert "link" not in magic  # but nothing was sent


# --- SES/SNS webhook -------------------------------------------------------

def _post_sns(client, payload):
    return client.post("/webhooks/ses", data=json.dumps(payload), content_type="application/json")


def test_webhook_suppresses_on_complaint(client, app):
    from app.suppression import is_suppressed

    inner = {
        "notificationType": "Complaint",
        "complaint": {"complainedRecipients": [{"emailAddress": "Mad@Example.com"}]},
    }
    r = _post_sns(client, {"Type": "Notification", "Message": json.dumps(inner)})
    assert r.status_code == 200
    with app.app_context():
        assert is_suppressed("mad@example.com") is True


def test_webhook_suppresses_permanent_bounce_only(client, app):
    from app.suppression import is_suppressed

    perm = {
        "notificationType": "Bounce",
        "bounce": {"bounceType": "Permanent", "bouncedRecipients": [{"emailAddress": "gone@example.com"}]},
    }
    transient = {
        "notificationType": "Bounce",
        "bounce": {"bounceType": "Transient", "bouncedRecipients": [{"emailAddress": "busy@example.com"}]},
    }
    _post_sns(client, {"Type": "Notification", "Message": json.dumps(perm)})
    _post_sns(client, {"Type": "Notification", "Message": json.dumps(transient)})
    with app.app_context():
        assert is_suppressed("gone@example.com") is True
        assert is_suppressed("busy@example.com") is False  # soft bounce kept


def test_webhook_confirms_subscription(client, monkeypatch):
    from app import webhooks

    seen = {}
    monkeypatch.setattr(webhooks.requests, "get", lambda url, **k: seen.setdefault("url", url))
    sub_url = "https://sns.eu-west-1.amazonaws.com/?Action=ConfirmSubscription&Token=abc"
    r = _post_sns(client, {"Type": "SubscriptionConfirmation", "SubscribeURL": sub_url})
    assert r.status_code == 200
    assert seen.get("url") == sub_url


def test_webhook_rejects_wrong_topic(client, app):
    app.config["SES_SNS_TOPIC_ARN"] = "arn:aws:sns:eu-west-1:1:correct"
    r = _post_sns(client, {"Type": "Notification", "TopicArn": "arn:aws:sns:eu-west-1:1:evil", "Message": "{}"})
    assert r.status_code == 403


def test_sns_cert_url_guard_blocks_ssrf():
    from app.webhooks import _is_aws_sns_url

    assert _is_aws_sns_url("https://sns.us-east-1.amazonaws.com/cert.pem") is True
    assert _is_aws_sns_url("https://evil.example.com/cert.pem") is False
    assert _is_aws_sns_url("http://sns.us-east-1.amazonaws.com/cert.pem") is False  # not https
    assert _is_aws_sns_url("https://sns.us-east-1.amazonaws.com.evil.com/x") is False
