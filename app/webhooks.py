"""Amazon SNS webhook for SES bounce/complaint notifications.

When SES is wired to an SNS topic, complaints and permanent bounces are POSTed
here. We verify the SNS signature (so the suppression list can't be poisoned by
forged requests), then record complained / hard-bounced addresses so the login
flow stops emailing them.

The endpoint is public (SNS has no credentials) and CSRF-exempt (applied in the
app factory). Its trust comes from SNS signature verification, not a session.
"""
from __future__ import annotations

import base64
import json
import logging
import re
from urllib.parse import urlparse

import requests
from flask import Blueprint, abort, current_app, request

from .suppression import suppress

logger = logging.getLogger("emf_hunt.webhooks")

bp = Blueprint("webhooks", __name__)

# SNS signing cert / subscribe URLs must live on an AWS SNS host (anti-SSRF).
_AWS_SNS_HOST = re.compile(r"^sns\.[a-z0-9-]+\.amazonaws\.com(\.cn)?$")

# Fields included in the SNS "string to sign", by message Type.
_SIGN_FIELDS = {
    "Notification": ["Message", "MessageId", "Subject", "Timestamp", "TopicArn", "Type"],
    "SubscriptionConfirmation": [
        "Message", "MessageId", "SubscribeURL", "Timestamp", "Token", "TopicArn", "Type",
    ],
    "UnsubscribeConfirmation": [
        "Message", "MessageId", "SubscribeURL", "Timestamp", "Token", "TopicArn", "Type",
    ],
}


def _is_aws_sns_url(url: str | None) -> bool:
    if not url:
        return False
    parsed = urlparse(url)
    return parsed.scheme == "https" and bool(_AWS_SNS_HOST.match(parsed.netloc))


def _string_to_sign(msg: dict) -> str | None:
    fields = _SIGN_FIELDS.get(msg.get("Type", ""))
    if fields is None:
        return None
    parts = []
    for key in fields:
        if key == "Subject" and "Subject" not in msg:
            continue  # Subject is optional and omitted when absent
        if key not in msg:
            return None
        parts.append(f"{key}\n{msg[key]}\n")
    return "".join(parts)


def _verify_signature(msg: dict) -> bool:
    cert_url = msg.get("SigningCertURL") or msg.get("SigningCertUrl")
    if not _is_aws_sns_url(cert_url):
        return False
    string_to_sign = _string_to_sign(msg)
    signature = msg.get("Signature")
    if string_to_sign is None or not signature:
        return False
    try:
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.asymmetric import padding
        from cryptography.x509 import load_pem_x509_certificate

        cert_pem = requests.get(cert_url, timeout=5).content
        public_key = load_pem_x509_certificate(cert_pem).public_key()
        algo = hashes.SHA256() if msg.get("SignatureVersion") == "2" else hashes.SHA1()
        public_key.verify(
            base64.b64decode(signature), string_to_sign.encode(), padding.PKCS1v15(), algo
        )
        return True
    except Exception as exc:
        logger.warning("SNS signature verification failed: %s", exc)
        return False


def _record_ses_event(message: dict) -> None:
    event = message.get("notificationType") or message.get("eventType")
    if event == "Complaint":
        for r in message.get("complaint", {}).get("complainedRecipients", []):
            suppress(r.get("emailAddress", ""), "complaint")
    elif event == "Bounce":
        bounce = message.get("bounce", {})
        if bounce.get("bounceType") == "Permanent":
            for r in bounce.get("bouncedRecipients", []):
                suppress(r.get("emailAddress", ""), "bounce")


@bp.post("/webhooks/ses")
def ses_notifications():
    try:
        msg = json.loads(request.get_data(as_text=True))
    except (ValueError, TypeError):
        abort(400)
    if not isinstance(msg, dict):
        abort(400)

    expected_topic = current_app.config.get("SES_SNS_TOPIC_ARN")
    if expected_topic and msg.get("TopicArn") != expected_topic:
        abort(403)

    if current_app.config.get("SES_WEBHOOK_VERIFY", True) and not _verify_signature(msg):
        abort(400)

    msg_type = msg.get("Type")
    if msg_type == "SubscriptionConfirmation":
        # Confirm the subscription by visiting the (validated) SubscribeURL.
        sub_url = msg.get("SubscribeURL")
        if _is_aws_sns_url(sub_url):
            try:
                requests.get(sub_url, timeout=5)
            except Exception as exc:
                logger.warning("Failed to confirm SNS subscription: %s", exc)
        return "", 200

    if msg_type == "Notification":
        try:
            inner = json.loads(msg.get("Message", "{}"))
        except (ValueError, TypeError):
            inner = {}
        if isinstance(inner, dict):
            _record_ses_event(inner)
        return "", 200

    # UnsubscribeConfirmation and anything else: acknowledge, do nothing.
    return "", 200
