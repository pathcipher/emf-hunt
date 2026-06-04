"""Pluggable email delivery.

- EMAIL_BACKEND=console  → development: the message (with the magic link) is written
  to the server log. No credentials needed.
- EMAIL_BACKEND=api      → production: POST to a transactional email provider's HTTP
  API. The JSON shape below is provider-generic; adapt `_send_api` to Mailgun /
  Postmark / Resend / SendGrid / SES as needed.
"""
from __future__ import annotations

import logging

import requests
from flask import current_app

logger = logging.getLogger("emf_hunt.email")


def send_email(to: str, subject: str, text: str, html: str | None = None) -> None:
    backend = current_app.config.get("EMAIL_BACKEND", "console")
    if backend == "api":
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
    subject = "Your EMF Hunt login link"
    text = (
        "Tap the link below to log in to EMF Hunt. It expires shortly and can only be "
        f"used once:\n\n{link}\n\nIf you didn't request this, you can ignore this email."
    )
    html = (
        "<p>Tap to log in to <strong>EMF Hunt</strong> — expires shortly, single use:</p>"
        f'<p><a href="{link}">Log in to EMF Hunt</a></p>'
        "<p>If you didn't request this, you can ignore this email.</p>"
    )
    send_email(email, subject, text, html)
