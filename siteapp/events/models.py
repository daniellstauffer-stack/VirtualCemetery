"""Models for private funeral contact lists, funeral events, and idempotent one-time invitation deliveries."""
from __future__ import annotations

import secrets
import uuid
from django.conf import settings
from django.db import models


def generate_opt_out_token():
    return secrets.token_urlsafe(24)


class FuneralContact(models.Model):
    """Private recipient on a person's funeral guest list. Strictly private to owner & authorized organizer."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="funeral_contacts",
    )
    full_name = models.CharField(max_length=150)
    email = models.EmailField()
    relationship = models.CharField(max_length=100, blank=True)
    source = models.CharField(max_length=60, default="Manual entry")
    opted_out = models.BooleanField(default=False)
    opt_out_token = models.CharField(max_length=64, unique=True, default=generate_opt_out_token)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["full_name", "email"]
        constraints = [
            models.UniqueConstraint(fields=["owner", "email"], name="uniq_funeral_contact_owner_email")
        ]

    def save(self, *args, **kwargs):
        self.email = (self.email or "").strip().lower()
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"{self.full_name} <{self.email}>"


class FuneralEvent(models.Model):
    """Funeral or memorial gathering details, completely separate from Memorial publication."""

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft — not yet sent"
        CONFIRMED = "confirmed", "Confirmed by organizer"
        CANCELLED = "cancelled", "Cancelled"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="funeral_events",
    )
    organizer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="organized_funeral_events",
    )
    title = models.CharField(max_length=180, default="Celebration of Life & Gathering")
    event_datetime = models.DateTimeField(null=True, blank=True)
    time_zone = models.CharField(max_length=64, default="America/Los_Angeles")
    location_name = models.CharField(max_length=180, blank=True)
    location_address = models.TextField(blank=True)
    livestream_url = models.URLField(
        blank=True,
        help_text="Kept strictly private to invited event recipients.",
    )
    invitation_wording = models.TextField(
        blank=True,
        help_text="Message included in each individual invitation email.",
    )
    version = models.PositiveIntegerField(default=1)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.title} (v{self.version}) for {self.owner.full_display_name}"


class InvitationDelivery(models.Model):
    """Idempotent one-time delivery record for a specific (event, version, contact)."""

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        QUEUED = "queued", "Queued for individual delivery"
        SENT = "sent", "Delivered"
        FAILED = "failed", "Delivery failed"
        BOUNCED = "bounced", "Bounced"
        NEEDS_RECONCILIATION = "needs_reconciliation", "Ambiguous timeout — needs reconciliation before retry"
        CANCELLED = "cancelled", "Cancelled"
        OPTED_OUT = "opted_out", "Skipped (recipient opted out)"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    event = models.ForeignKey(FuneralEvent, on_delete=models.CASCADE, related_name="deliveries")
    event_version = models.PositiveIntegerField(default=1)
    contact = models.ForeignKey(FuneralContact, on_delete=models.CASCADE, related_name="deliveries")
    recipient_email = models.EmailField()
    recipient_name = models.CharField(max_length=150)
    idempotency_key = models.CharField(max_length=160, unique=True)
    status = models.CharField(max_length=30, choices=Status.choices, default=Status.QUEUED, db_index=True)
    provider_message_id = models.CharField(max_length=160, blank=True)
    last_error = models.TextField(blank=True)
    attempt_count = models.PositiveIntegerField(default=0)
    sent_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["event", "event_version", "contact"],
                name="uniq_delivery_event_version_contact",
            )
        ]
        indexes = [
            models.Index(fields=["event", "status"]),
        ]

    @staticmethod
    def build_idempotency_key(event: FuneralEvent, contact: FuneralContact) -> str:
        return f"vc-event-{event.id}-v{event.version}-contact-{contact.id}"
