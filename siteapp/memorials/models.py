"""Models for published memorials (strictly separate from My Plan), guestbooks, and relationships."""
from __future__ import annotations

import secrets
import uuid
from datetime import timedelta
from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.text import slugify


def default_memorial_invite_expiry():
    return timezone.now() + timedelta(days=30)


def generate_invite_token():
    return secrets.token_urlsafe(32)


class Memorial(models.Model):
    """Published approved snapshot of a person's memorial.

    Completely decoupled from LifePlan so edits to private planning data never
    leak onto a memorial page.
    """

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft (steward preparing release)"
        PUBLISHED = "published", "Published"
        SUSPENDED = "suspended", "Suspended / Unpublished"

    class Audience(models.TextChoices):
        INVITED_ONLY = "invited_only", "Invited family and friends only"
        PUBLIC = "public", "Public memorial"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="memorial",
    )
    person_id = models.UUIDField(db_index=True, default=uuid.uuid4)
    slug = models.SlugField(max_length=140, unique=True)

    # Published snapshot fields
    full_name = models.CharField(max_length=160)
    birth_year = models.PositiveIntegerField(null=True, blank=True)
    death_year = models.PositiveIntegerField(null=True, blank=True)
    biography = models.TextField(blank=True)
    steward_tribute = models.TextField(
        blank=True,
        help_text="Optional family-written tribute added by the steward with its own author credit.",
    )
    steward_tribute_author = models.CharField(max_length=150, blank=True)

    portrait_storage_path = models.CharField(max_length=300, blank=True)
    portrait_static_asset = models.CharField(max_length=120, blank=True)
    portrait_alt_text = models.CharField(max_length=200, blank=True)

    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT, db_index=True)
    audience = models.CharField(
        max_length=20,
        choices=Audience.choices,
        default=Audience.INVITED_ONLY,
        db_index=True,
    )
    allow_site_search = models.BooleanField(default=False, db_index=True)
    guestbook_open = models.BooleanField(default=True)
    guestbook_requires_approval = models.BooleanField(default=True)

    # Family-created memorial provenance (for loved ones who died without an account)
    is_family_created = models.BooleanField(default=False)
    created_by_label = models.CharField(max_length=160, blank=True)

    published_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="published_memorials",
    )
    published_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-published_at", "full_name"]
        indexes = [
            models.Index(fields=["status", "audience", "allow_site_search"]),
        ]

    @property
    def life_dates_display(self) -> str:
        if self.birth_year and self.death_year:
            return f"{self.birth_year} – {self.death_year}"
        if self.birth_year:
            return f"Born {self.birth_year}"
        if self.death_year:
            return f"Remembered {self.death_year}"
        return ""

    def save(self, *args, **kwargs):
        if not self.slug:
            base = slugify(self.full_name) or "memorial"
            self.slug = f"{base}-{str(self.person_id)[:6]}"
        # Enforce invariant: non-public memorials can NEVER be searchable
        if self.audience != self.Audience.PUBLIC or self.status != self.Status.PUBLISHED:
            self.allow_site_search = False
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"Memorial: {self.full_name} ({self.status})"


class PublishedMemory(models.Model):
    """Approved snapshot copy of a single selected memory on a Published Memorial."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    memorial = models.ForeignKey(Memorial, on_delete=models.CASCADE, related_name="published_memories")
    source_plan_memory_id = models.UUIDField(null=True, blank=True)
    title = models.CharField(max_length=180)
    year_taken = models.CharField(max_length=32, blank=True)
    story = models.TextField(blank=True)
    alt_text = models.CharField(max_length=240)
    display_media_path = models.CharField(max_length=300, blank=True)
    static_sample_image = models.CharField(max_length=120, blank=True)
    display_order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["display_order", "created_at"]

    def __str__(self) -> str:
        return f"{self.title} on {self.memorial.full_name}"


class MemorialInvite(models.Model):
    """Expiring invitation bound to an intended recipient for viewing an invited-only memorial."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    memorial = models.ForeignKey(Memorial, on_delete=models.CASCADE, related_name="invites")
    invited_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="sent_memorial_invites",
    )
    intended_email = models.EmailField()
    intended_name = models.CharField(max_length=150, blank=True)
    token = models.CharField(max_length=80, unique=True, default=generate_invite_token)
    expires_at = models.DateTimeField(default=default_memorial_invite_expiry)
    redeemed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="redeemed_memorial_invites",
    )
    redeemed_at = models.DateTimeField(null=True, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["memorial", "intended_email", "revoked_at"]),
        ]

    @property
    def is_redeemable(self) -> bool:
        return (
            self.revoked_at is None
            and self.redeemed_at is None
            and timezone.now() <= self.expires_at
        )

    @property
    def grants_active_access(self) -> bool:
        return self.revoked_at is None and self.redeemed_by_id is not None


class GuestbookEntry(models.Model):
    """Virtual flower and/or guestbook note left by a signed-in visitor."""

    class FlowerChoice(models.TextChoices):
        NONE = "", "Note only (no flower)"
        WHITE_LILY = "white_lily", "White Lily — Peace & remembrance"
        WILD_ROSE = "wild_rose", "Garden Rose — Love & gratitude"
        OLIVE_BRANCH = "olive_branch", "Olive Branch — Quiet strength"
        FORGET_ME_NOT = "forget_me_not", "Forget-Me-Not — Lasting memory"
        MARIGOLD = "marigold", "Golden Marigold — Warmth & light"

    class ModerationStatus(models.TextChoices):
        PENDING = "pending", "Awaiting steward approval"
        APPROVED = "approved", "Visible on memorial"
        HIDDEN = "hidden", "Hidden by steward"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    memorial = models.ForeignKey(Memorial, on_delete=models.CASCADE, related_name="guestbook_entries")
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="guestbook_contributions",
    )
    author_display_name = models.CharField(max_length=150)
    relationship_note = models.CharField(max_length=120, blank=True)
    flower = models.CharField(max_length=32, choices=FlowerChoice.choices, default=FlowerChoice.WHITE_LILY, blank=True)
    message = models.TextField(blank=True)
    status = models.CharField(
        max_length=20,
        choices=ModerationStatus.choices,
        default=ModerationStatus.PENDING,
        db_index=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["memorial", "status", "-created_at"]),
        ]

    def __str__(self) -> str:
        return f"Tribute by {self.author_display_name} on {self.memorial.full_name} ({self.status})"


class AbuseReport(models.Model):
    """Visitor abuse or takedown report on a guestbook entry or memorial."""

    class Status(models.TextChoices):
        OPEN = "open", "Open"
        ACTION_TAKEN = "action_taken", "Action taken"
        DISMISSED = "dismissed", "Dismissed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    memorial = models.ForeignKey(Memorial, on_delete=models.CASCADE, related_name="abuse_reports")
    guestbook_entry = models.ForeignKey(
        GuestbookEntry,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="abuse_reports",
    )
    reported_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    reason = models.TextField()
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.OPEN)
    created_at = models.DateTimeField(auto_now_add=True)


class MemorialRelationship(models.Model):
    """Opt-in bilateral relationship link between two memorials.

    Both owners or authorized stewards must agree. Shown ONLY to viewers
    permitted to see BOTH endpoints. Either side may withdraw. Grants NO plan access.
    """

    class Status(models.TextChoices):
        PROPOSED = "proposed", "Proposed — awaiting consent from other side"
        ACCEPTED = "accepted", "Accepted by both sides"
        WITHDRAWN = "withdrawn", "Withdrawn"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    from_memorial = models.ForeignKey(
        Memorial, on_delete=models.CASCADE, related_name="outgoing_relationships"
    )
    to_memorial = models.ForeignKey(
        Memorial, on_delete=models.CASCADE, related_name="incoming_relationships"
    )
    label_from_to = models.CharField(
        max_length=100,
        help_text="How the first person relates to the second (e.g., 'Husband of', 'Lifelong friend of').",
    )
    label_to_from = models.CharField(
        max_length=100,
        help_text="Reciprocal label (e.g., 'Wife of', 'Lifelong friend of').",
    )
    proposed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="proposed_relationships",
    )
    from_approved = models.BooleanField(default=True)
    to_approved = models.BooleanField(default=False)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PROPOSED)
    withdrawn_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def accept_target_side(self):
        self.to_approved = True
        if self.from_approved and self.to_approved:
            self.status = self.Status.ACCEPTED
        self.save(update_fields=["to_approved", "status"])

    def withdraw(self):
        self.status = self.Status.WITHDRAWN
        self.withdrawn_at = timezone.now()
        self.save(update_fields=["status", "withdrawn_at"])
