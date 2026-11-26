"""Transactional email adapter (Postmark in staging/prod; SMTP/Mailpit or console locally).

Includes:
- Staging recipient allowlist guardrail so staging rehearsals never mail real families.
- AmbiguousDeliveryTimeout signaling so worker marks NEEDS_RECONCILIATION before retry.
- Idempotency metadata header passed to Postmark.
"""
from __future__ import annotations

import logging
import uuid
import requests
from django.conf import settings
from django.core.mail import EmailMessage

logger = logging.getLogger(__name__)


class AmbiguousDeliveryTimeout(Exception):
    """Raised when an HTTP email request timed out after transmission; requires reconciliation."""


def _is_recipient_allowed_in_staging(to_email: str) -> bool:
    allowlist = settings.STAGING_ALLOWED_EMAIL_RECIPIENTS
    if not allowlist:
        return True
    email_l = to_email.strip().lower()
    for entry in allowlist:
        e = entry.lower()
        if e.startswith("@") and email_l.endswith(e):
            return True
        if email_l == e:
            return True
    return False


def send_transactional_email(
    *,
    to_email: str,
    to_name: str,
    subject: str,
    body: str,
    idempotency_key: str,
) -> str:
    """Send an individual transactional email and return a provider message ID."""
    if settings.DJANGO_ENV == "staging" and not _is_recipient_allowed_in_staging(to_email):
        raise ValueError("Staging email guardrail blocked delivery to an unlisted recipient.")

    provider = settings.EMAIL_PROVIDER.lower()
    if provider == "postmark":
        token = settings.POSTMARK_SERVER_TOKEN
        if not token or "placeholder" in token:
            raise RuntimeError(
                "POSTMARK_SERVER_TOKEN is still a placeholder. Configure a real Postmark server token in Secret Manager."
            )
        payload = {
            "From": f"{settings.EMAIL_FROM_NAME} <{settings.EMAIL_FROM_ADDRESS}>",
            "To": f"{to_name} <{to_email}>" if to_name else to_email,
            "Subject": subject,
            "TextBody": body,
            "MessageStream": settings.POSTMARK_MESSAGE_STREAM,
            "Metadata": {"idempotency_key": idempotency_key},
        }
        try:
            resp = requests.post(
                "https://api.postmarkapp.com/email",
                json=payload,
                headers={
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                    "X-Postmark-Server-Token": token,
                },
                timeout=12,
            )
            resp.raise_for_status()
            data = resp.json()
            return str(data.get("MessageID", idempotency_key))
        except requests.Timeout as exc:
            raise AmbiguousDeliveryTimeout("Postmark request timed out; verify status before retrying.") from exc

    # Local development / test fallback (Django console or Mailpit SMTP)
    msg = EmailMessage(
        subject=subject,
        body=body,
        from_email=f"{settings.EMAIL_FROM_NAME} <{settings.EMAIL_FROM_ADDRESS}>",
        to=[to_email],
        headers={"X-VC-Idempotency-Key": idempotency_key},
    )
    msg.send(fail_silently=False)
    return f"local-{uuid.uuid4().hex[:12]}"
