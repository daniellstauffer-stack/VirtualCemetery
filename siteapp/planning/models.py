"""Models for My Plan (private planning), draft memories, and the Draft My Wishes worksheet."""
from __future__ import annotations

import uuid
from django.conf import settings
from django.db import models

from siteapp.storage import get_media_storage


def memory_original_upload_path(instance: "PlanMemory", filename: str) -> str:
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else "jpg"
    return f"originals/{instance.plan.owner.person_id}/{instance.id}.{ext}"


def memory_display_upload_path(instance: "PlanMemory", filename: str) -> str:
    return f"display/{instance.plan.owner.person_id}/{instance.id}.jpg"


def portrait_upload_path(instance: "LifePlan", filename: str) -> str:
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else "jpg"
    return f"portraits/{instance.owner.person_id}/{uuid.uuid4()}.{ext}"


class LifePlan(models.Model):
    """Private workspace for a living person. Strictly separate from Published Memorial."""

    class DispositionChoice(models.TextChoices):
        UNDECIDED = "undecided", "Undecided / discuss with family"
        BURIAL = "burial", "Traditional burial"
        CREMATION = "cremation", "Cremation"
        GREEN_BURIAL = "green_burial", "Natural / green burial"
        BODY_DONATION = "body_donation", "Medical or scientific donation"

    class MemorialAudienceCeiling(models.TextChoices):
        INVITED_ONLY = "invited_only", "Invited family and friends only (recommended default)"
        PUBLIC = "public", "Public memorial (anyone with the link may view)"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="life_plan",
    )

    # Draft memorial identity (not published until verified death & steward publish)
    memorial_preferred_name = models.CharField(max_length=160, blank=True)
    birth_year = models.PositiveIntegerField(null=True, blank=True)
    biography_draft = models.TextField(blank=True)
    portrait_file = models.FileField(
        upload_to=portrait_upload_path,
        storage=get_media_storage,
        blank=True,
        null=True,
    )
    portrait_static_asset = models.CharField(
        max_length=120,
        blank=True,
        help_text="Optional path under static/images/ for pilot demonstration records.",
    )
    portrait_alt_text = models.CharField(max_length=200, blank=True)

    # Private end-of-life preferences
    disposition_preference = models.CharField(
        max_length=30,
        choices=DispositionChoice.choices,
        default=DispositionChoice.UNDECIDED,
    )
    disposition_notes = models.TextField(
        blank=True,
        help_text="Private notes on burial, cremation, cemetery plot, or scattering wishes.",
    )
    service_wishes = models.TextField(
        blank=True,
        help_text="Readings, music, gathering style, or people you would like involved.",
    )
    emergency_contacts = models.TextField(
        blank=True,
        help_text="Names, relationships, and phone numbers of people to notify first.",
    )
    important_document_locations = models.TextField(
        blank=True,
        help_text="Where paper wills, deeds, or insurance policies are kept. Do NOT store passwords or full account numbers here.",
    )

    # Audience ceiling chosen by owner — a steward cannot widen beyond this
    memorial_audience_ceiling = models.CharField(
        max_length=24,
        choices=MemorialAudienceCeiling.choices,
        default=MemorialAudienceCeiling.INVITED_ONLY,
    )
    allow_site_search = models.BooleanField(
        default=False,
        help_text="Explicitly allow a published public memorial to appear in Virtual Cemetery's search.",
    )
    guestbook_requires_approval = models.BooleanField(
        default=True,
        help_text="Require your steward to approve guestbook notes before they appear.",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:
        return f"LifePlan for {self.owner.full_display_name}"

    @property
    def display_memorial_name(self) -> str:
        return self.memorial_preferred_name.strip() or self.owner.full_display_name


class PlanMemory(models.Model):
    """A photograph and story held in My Plan with an explicit per-item audience choice."""

    class Audience(models.TextChoices):
        PRIVATE_ONLY = "private_only", "Only me (stays private forever, never released)"
        STEWARD_AFTER_DEATH = "steward_after_death", "Shared only with my steward after verified death"
        INVITED_MEMORIAL = "invited_memorial", "May appear on my memorial for invited family"
        PUBLIC_MEMORIAL = "public_memorial", "May appear on my memorial (up to my memorial audience setting)"

    class MediaStatus(models.TextChoices):
        READY = "ready", "Processed & EXIF-stripped"
        PROCESSING = "processing", "Processing"
        REJECTED = "rejected", "Rejected"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    plan = models.ForeignKey(LifePlan, on_delete=models.CASCADE, related_name="memories")
    title = models.CharField(max_length=180)
    story = models.TextField(blank=True)
    year_taken = models.CharField(max_length=32, blank=True)
    alt_text = models.CharField(
        max_length=240,
        help_text="Describe this photograph for visitors using screen readers.",
    )
    photo_original = models.FileField(
        upload_to=memory_original_upload_path,
        storage=get_media_storage,
        blank=True,
        null=True,
    )
    photo_display = models.FileField(
        upload_to=memory_display_upload_path,
        storage=get_media_storage,
        blank=True,
        null=True,
    )
    static_sample_image = models.CharField(max_length=120, blank=True)
    audience = models.CharField(
        max_length=32,
        choices=Audience.choices,
        default=Audience.PRIVATE_ONLY,
    )
    owner_confirmed_rights = models.BooleanField(
        default=False,
        help_text="Owner confirmed they hold the rights or permission to store and share this item.",
    )
    source_label = models.CharField(max_length=80, default="Added directly")
    source_external_id = models.CharField(max_length=180, blank=True, db_index=True)
    media_status = models.CharField(
        max_length=20,
        choices=MediaStatus.choices,
        default=MediaStatus.READY,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.title} ({self.get_audience_display()})"

    @property
    def is_eligible_for_memorial(self) -> bool:
        return self.audience in (
            self.Audience.INVITED_MEMORIAL,
            self.Audience.PUBLIC_MEMORIAL,
        )

    @property
    def is_released_to_steward_after_death(self) -> bool:
        return self.audience != self.Audience.PRIVATE_ONLY

    def audience_plain_summary(self) -> str:
        mapping = {
            self.Audience.PRIVATE_ONLY: "Only you can see this. Even after death, it stays private and is never shown to your steward or visitors.",
            self.Audience.STEWARD_AFTER_DEATH: "Only you can see this today. After a verified death, your steward may read it privately, but it is not placed on the public memorial.",
            self.Audience.INVITED_MEMORIAL: "Only you can see this today (and in your preview). After a verified death, your steward may publish it for invited family.",
            self.Audience.PUBLIC_MEMORIAL: "Only you can see this today (and in your preview). After a verified death, your steward may publish it within your memorial's audience ceiling.",
        }
        return mapping.get(self.audience, "")


class WishesWorksheet(models.Model):
    """Private 'Draft my wishes' preparation worksheet for meeting with estate counsel.

    Explicitly NOT a legally executed will. Avoids collecting passwords or full
    financial account numbers.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="wishes_worksheet",
    )
    jurisdiction = models.CharField(max_length=120, default="Oregon, United States")
    dependants_summary = models.TextField(
        blank=True,
        help_text="Spouse, minor children, adult dependants, or pets who rely on your care.",
    )
    proposed_guardians = models.TextField(
        blank=True,
        help_text="Primary and backup people you would like to discuss naming as guardians.",
    )
    asset_categories = models.TextField(
        blank=True,
        help_text="High-level categories only (e.g., family home, retirement accounts, workshop tools). Do NOT enter account numbers or passwords.",
    )
    intended_gifts = models.TextField(
        blank=True,
        help_text="Specific keepsakes, charitable gifts, or family heirlooms you want to discuss with counsel.",
    )
    executor_preferences = models.TextField(
        blank=True,
        help_text="Who you are considering as personal representative / executor, and an alternate.",
    )
    questions_for_counsel = models.TextField(
        blank=True,
        help_text="Questions to bring to your estate-planning attorney.",
    )
    completed_steps = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:
        return f"WishesWorksheet for {self.owner.full_display_name}"
