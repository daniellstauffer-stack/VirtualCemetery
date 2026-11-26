"""Models for voluntary site contributions (Stripe idempotency) and curated local professional directory."""
from __future__ import annotations

import uuid
from django.conf import settings
from django.db import models


class SiteContribution(models.Model):
    """Voluntary one-time contribution to support Virtual Cemetery hosting & operations.

    Paying has ZERO bearing on memorial access. Strictly idempotent by Stripe
    event/session ID so replayed webhooks never duplicate a contribution.
    """

    class Status(models.TextChoices):
        PENDING = "pending", "Pending checkout"
        COMPLETED = "completed", "Completed"
        REFUNDED = "refunded", "Refunded"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    contributor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="site_contributions",
    )
    contributor_email = models.EmailField(blank=True)
    stripe_session_id = models.CharField(max_length=160, unique=True)
    stripe_event_id = models.CharField(max_length=160, unique=True, null=True, blank=True)
    amount_cents = models.PositiveIntegerField()
    currency = models.CharField(max_length=8, default="usd")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    @property
    def amount_display(self) -> str:
        return f"${self.amount_cents / 100:,.2f} {self.currency.upper()}"


class DirectoryProvider(models.Model):
    """Curated pilot directory entry for funeral homes and estate-planning attorneys."""

    class Category(models.TextChoices):
        FUNERAL_HOME = "funeral_home", "Funeral home & memorial services"
        ESTATE_LAWYER = "estate_lawyer", "Estate-planning attorney"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    category = models.CharField(max_length=24, choices=Category.choices, db_index=True)
    name = models.CharField(max_length=180)
    city = models.CharField(max_length=100, db_index=True)
    state = models.CharField(max_length=50, default="OR")
    postal_code = models.CharField(max_length=20, db_index=True)
    verified_specialty = models.CharField(max_length=180, blank=True)
    phone = models.CharField(max_length=40, blank=True)
    website = models.URLField(blank=True)
    rating = models.DecimalField(max_digits=3, decimal_places=1, null=True, blank=True)
    review_count = models.PositiveIntegerField(default=0)
    review_source = models.CharField(max_length=100, blank=True)
    licensing_lookup_url = models.URLField(blank=True)
    is_paid_placement = models.BooleanField(default=False)
    google_place_id = models.CharField(max_length=120, blank=True)

    class Meta:
        ordering = ["-rating", "name"]

    def __str__(self) -> str:
        return f"{self.name} ({self.city}, {self.state})"
