"""Pluggable email delivery.

- EMAIL_BACKEND=console  → development: the message (with the magic link) is written
  to the server log. No credentials needed.
- EMAIL_BACKEND=ses      → AWS SES (Simple Email Service). Requires AWS credentials
  (AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_DEFAULT_REGION env vars).
- EMAIL_BACKEND=api      → production: POST to a transactional email provider's HTTP
  API. The JSON shape below is provider-generic; adapt `_send_api` to Mailgun /
  Postmark / Resend / etc. as needed.
"""
from __future__ import annotations

import logging

import requests
from flask import current_app

logger = logging.getLogger("emf_hunt.email")


def send_email(to: str, subject: str, text: str, html: str | None = None) -> None:
    backend = current_app.config.get("EMAIL_BACKEND", "console")
    if backend == "ses":
        _send_ses(to, subject, text, html)
    elif backend == "api":
        _send_api(to, subject, text, html)
    else:
        _send_console(to, subject, text, html)


def _send_console(to: str, subject: str, text: str, html: str | None) -> None:
    logger.warning(
        "\n=== DEV EMAIL (console backend) ===\n"
        "To: %s\nSubject: %s\n\n%s\n"
        "===================================",
        to,
        subject,
        text,
    )


def _send_ses(to: str, subject: str, text: str, html: str | None) -> None:
    try:
        import boto3
    except ImportError:
        raise RuntimeError(
            "EMAIL_BACKEND=ses requires boto3. Install it with: pip install boto3"
        )
    client = boto3.client("ses")
    client.send_email(
        Source=current_app.config["EMAIL_FROM"],
        Destination={"ToAddresses": [to]},
        Message={
            "Subject": {"Data": subject},
            "Body": {
                "Text": {"Data": text},
                "Html": {"Data": html or text},
            },
        },
    )


def _send_api(to: str, subject: str, text: str, html: str | None) -> None:
    url = current_app.config.get("EMAIL_API_URL")
    key = current_app.config.get("EMAIL_API_KEY")
    if not url or not key:
        raise RuntimeError(
            "EMAIL_BACKEND=api but EMAIL_API_URL / EMAIL_API_KEY are not configured"
        )
    resp = requests.post(
        url,
        headers={"Authorization": f"Bearer {key}"},
        json={
            "from": current_app.config["EMAIL_FROM"],
            "to": to,
            "subject": subject,
            "text": text,
            "html": html or text,
        },
        timeout=10,
    )
    resp.raise_for_status()


def send_magic_link(email: str, link: str) -> None:
    site = current_app.config["SITE_NAME"]
    subject = f"Your {site} login link"
    text = (
        f"Tap the link below to log in to {site}. It expires shortly and can only be "
        f"used once:\n\n{link}\n\nIf you didn't request this, you can ignore this email."
    )
    html = (
        f"<p>Tap to log in to <strong>{site}</strong> — expires shortly, single use:</p>"
        f'<p><a href="{link}">Log in to {site}</a></p>'
        "<p>If you didn't request this, you can ignore this email.</p>"
    )
    send_email(email, subject, text, html)
