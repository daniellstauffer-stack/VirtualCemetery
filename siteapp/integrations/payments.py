"""Stripe Hosted Checkout adapter & idempotent webhook fulfillment for voluntary site support."""
from __future__ import annotations

import hashlib
import hmac
import json
from django.conf import settings
from django.db import transaction

from siteapp.accounts.models import record_audit

from .models import SiteContribution


def create_checkout_session(*, amount_cents: int, user, success_url: str, cancel_url: str) -> dict:
    """Create a Stripe Hosted Checkout session (or sandbox preview when STRIPE_ENABLED=False)."""
    if amount_cents < 100 or amount_cents > 500000:
        raise ValueError("Contribution amount must be between $1 and $5,000.")

    if not settings.STRIPE_ENABLED or "placeholder" in settings.STRIPE_SECRET_KEY:
        return {
            "mode": "placeholder",
            "message": (
                "Stripe Hosted Checkout is currently in placeholder mode. Configure STRIPE_ENABLED=True "
                "and real Stripe keys in Secret Manager to accept live voluntary contributions."
            ),
            "amount_cents": amount_cents,
            "currency": settings.STRIPE_CURRENCY,
        }

    import stripe

    stripe.api_key = settings.STRIPE_SECRET_KEY
    session = stripe.checkout.Session.create(
        mode="payment",
        payment_method_types=["card"],
        line_items=[
            {
                "price_data": {
                    "currency": settings.STRIPE_CURRENCY,
                    "unit_amount": amount_cents,
                    "product_data": {
                        "name": f"Voluntary support for {settings.OPERATOR_NAME}",
                        "description": "One-time voluntary contribution. Has no bearing on memorial access.",
                    },
                },
                "quantity": 1,
            }
        ],
        customer_email=user.email if (user and user.is_authenticated) else None,
        success_url=success_url,
        cancel_url=cancel_url,
    )
    SiteContribution.objects.get_or_create(
        stripe_session_id=session.id,
        defaults={
            "contributor": user if (user and user.is_authenticated) else None,
            "contributor_email": user.email if (user and user.is_authenticated) else "",
            "amount_cents": amount_cents,
            "currency": settings.STRIPE_CURRENCY,
            "status": SiteContribution.Status.PENDING,
        },
    )
    return {"mode": "live", "checkout_url": session.url, "session_id": session.id}


def verify_stripe_signature(payload_bytes: bytes, sig_header: str, secret: str) -> bool:
    """Verify HMAC-SHA256 Stripe-style webhook signature (supports test & live headers)."""
    if not sig_header or not secret:
        return False
    parts = dict(item.split("=", 1) for item in sig_header.split(",") if "=" in item)
    timestamp = parts.get("t", "")
    v1 = parts.get("v1", "")
    if not timestamp or not v1:
        return False
    signed = f"{timestamp}.".encode("utf-8") + payload_bytes
    expected = hmac.new(secret.encode("utf-8"), signed, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, v1)


@transaction.atomic
def process_stripe_webhook(payload_bytes: bytes, sig_header: str) -> tuple[SiteContribution | None, bool]:
    """Verify signed Stripe webhook notification and idempotently record ONE contribution.

    Returns `(contribution, created_or_updated)`. Replaying the exact same
    event or session returns `(existing_contribution, False)` with zero duplicates.
    """
    if not verify_stripe_signature(payload_bytes, sig_header, settings.STRIPE_WEBHOOK_SECRET):
        raise PermissionError("Invalid Stripe webhook signature.")

    event = json.loads(payload_bytes.decode("utf-8"))
    event_id = event.get("id", "")
    event_type = event.get("type", "")
    obj = event.get("data", {}).get("object", {})

    if event_type not in ("checkout.session.completed", "checkout.session.async_payment_succeeded"):
        return None, False

    session_id = obj.get("id", "")
    amount_total = int(obj.get("amount_total", 0))
    currency = (obj.get("currency") or "").lower()
    email = (obj.get("customer_email") or obj.get("customer_details", {}).get("email") or "").lower()

    if not session_id or amount_total <= 0 or currency != settings.STRIPE_CURRENCY.lower():
        raise ValueError("Webhook payment amount or currency did not match expected contribution.")

    # Idempotency check: if this event or completed session was already recorded, do nothing!
    if event_id:
        existing_evt = SiteContribution.objects.filter(stripe_event_id=event_id).first()
        if existing_evt:
            return existing_evt, False

    existing_sess = SiteContribution.objects.select_for_update().filter(stripe_session_id=session_id).first()
    if existing_sess:
        if existing_sess.status == SiteContribution.Status.COMPLETED:
            return existing_sess, False
        existing_sess.status = SiteContribution.Status.COMPLETED
        existing_sess.stripe_event_id = event_id or existing_sess.stripe_event_id
        existing_sess.save(update_fields=["status", "stripe_event_id", "updated_at"])
        record_audit(
            action="contribution.completed",
            summary=f"Voluntary contribution recorded ({existing_sess.amount_display}).",
            target_type="SiteContribution",
            target_id=existing_sess.id,
        )
        return existing_sess, True

    contrib = SiteContribution.objects.create(
        stripe_session_id=session_id,
        stripe_event_id=event_id or None,
        contributor_email=email,
        amount_cents=amount_total,
        currency=currency,
        status=SiteContribution.Status.COMPLETED,
    )
    record_audit(
        action="contribution.completed",
        summary=f"Voluntary contribution recorded ({contrib.amount_display}).",
        target_type="SiteContribution",
        target_id=contrib.id,
    )
    return contrib, True
