"""Models for steward assignments, private death reports, isolated evidence, and verification decisions."""
from __future__ import annotations

import secrets
import uuid
from datetime import timedelta
from django.conf import settings
from django.db import models
from django.utils import timezone

from siteapp.storage import get_evidence_storage


def default_invite_expiry():
    return timezone.now() + timedelta(days=14)


def default_evidence_purge_date():
    return timezone.now() + timedelta(days=settings.GCP_EVIDENCE_RETENTION_DAYS)


def generate_token():
    return secrets.token_urlsafe(32)


def evidence_upload_path(instance: "DeathReport", filename: str) -> str:
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else "pdf"
    return f"cases/{instance.id}/{uuid.uuid4()}.{ext}"


class StewardAssignment(models.Model):
    """Designation of a primary or backup memorial steward (and optional funeral organizer).

    Grants NO legal authority over an estate. Revoking immediately ends access.
    """

    class Role(models.TextChoices):
        PRIMARY = "primary", "Primary memorial steward"
        BACKUP = "backup", "Backup memorial steward"

    class Status(models.TextChoices):
        INVITED = "invited", "Invitation pending"
        ACCEPTED = "accepted", "Accepted"
        DECLINED = "declined", "Declined"
        REVOKED = "revoked", "Revoked by owner"
        EXPIRED = "expired", "Invitation expired"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="steward_assignments",
    )
    role = models.CharField(max_length=16, choices=Role.choices, default=Role.PRIMARY)
    invitee_name = models.CharField(max_length=150)
    invitee_email = models.EmailField()
    steward_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="accepted_stewardships",
    )
    can_organize_funeral = models.BooleanField(
        default=False,
        help_text="Also authorize this person as Funeral Organizer to arrange services and send invitations.",
    )
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.INVITED)
    invite_token = models.CharField(max_length=80, unique=True, default=generate_token)
    expires_at = models.DateTimeField(default=default_invite_expiry)
    accepted_at = models.DateTimeField(null=True, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["role", "-created_at"]
        indexes = [
            models.Index(fields=["owner", "status"]),
            models.Index(fields=["steward_user", "status"]),
            models.Index(fields=["invitee_email", "status"]),
        ]

    @property
    def is_invitation_redeemable(self) -> bool:
        return (
            self.status == self.Status.INVITED
            and self.revoked_at is None
            and timezone.now() <= self.expires_at
        )

    @property
    def is_currently_active(self) -> bool:
        return self.status == self.Status.ACCEPTED and self.revoked_at is None

    def revoke(self):
        self.status = self.Status.REVOKED
        self.revoked_at = timezone.now()
        self.save(update_fields=["status", "revoked_at"])

    def __str__(self) -> str:
        return f"{self.invitee_name} ({self.get_role_display()} for {self.owner.full_display_name})"


class DeathReport(models.Model):
    """Private death-verification case. Never triggers mail or alters public pages on submission."""

    class Status(models.TextChoices):
        SUBMITTED = "submitted", "Submitted — awaiting initial review"
        CHALLENGE_WINDOW = "challenge_window", "Owner challenge outreach sent"
        CONFLICT_PAUSED = "conflict_paused", "Paused — conflicting claim / second reviewer required"
        APPROVED = "approved", "Verified & approved"
        REJECTED = "rejected", "Rejected"
        REVERSED = "reversed", "Reversed after appeal / error correction"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    subject_owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="death_reports",
    )
    submitted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="submitted_death_reports",
    )
    submitter_relationship = models.CharField(max_length=120, default="Designated steward")
    reported_date_of_death = models.DateField(null=True, blank=True)
    evidence_summary = models.TextField(
        help_text="Description of independent evidence provided (e.g., certified record, obituary link, funeral home contact)."
    )
    evidence_file = models.FileField(
        upload_to=evidence_upload_path,
        storage=get_evidence_storage,
        blank=True,
        null=True,
    )
    evidence_purged_at = models.DateTimeField(null=True, blank=True)
    evidence_scheduled_purge_at = models.DateTimeField(default=default_evidence_purge_date)

    status = models.CharField(max_length=24, choices=Status.choices, default=Status.SUBMITTED)
    assigned_reviewer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assigned_death_cases",
    )
    second_reviewer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="second_reviewed_cases",
    )
    independent_evidence_checked = models.BooleanField(default=False)
    owner_challenge_sent_at = models.DateTimeField(null=True, blank=True)
    owner_challenge_channel = models.CharField(max_length=160, blank=True)
    erroneous_notices_snapshot = models.JSONField(
        default=list,
        blank=True,
        help_text="List of recipients who already received an invitation before a mistaken approval was reversed.",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"Case {str(self.id)[:8]} for {self.subject_owner.full_display_name} ({self.status})"


class VerificationDecision(models.Model):
    """Immutable log of each reviewer action and rationale on a DeathReport."""

    class Action(models.TextChoices):
        ASSIGNED = "assigned", "Case assigned to reviewer"
        CHALLENGE_SENT = "challenge_sent", "Owner challenge outreach sent"
        EVIDENCE_CHECKED = "evidence_checked", "Independent evidence verified"
        CONFLICT_PAUSED = "conflict_paused", "Case paused for second reviewer"
        APPROVED = "approved", "Death verified and approved"
        REJECTED = "rejected", "Report rejected"
        REVERSED = "reversed", "Approval reversed & owner restored"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    report = models.ForeignKey(DeathReport, on_delete=models.CASCADE, related_name="decisions")
    reviewer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="verification_decisions",
    )
    action = models.CharField(max_length=32, choices=Action.choices)
    reason = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]


class DisputeAppeal(models.Model):
    """Public or signed-in dispute/appeal submission so a living owner or family
    member can reach support WITHOUT signing into a disputed account.
    """

    class Status(models.TextChoices):
        OPEN = "open", "Open — urgent staff review"
        RESOLVED = "resolved", "Resolved"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    related_report = models.ForeignKey(
        DeathReport,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="disputes",
    )
    subject_email_or_name = models.CharField(max_length=180)
    claimant_name = models.CharField(max_length=150)
    claimant_email = models.EmailField()
    claimant_phone = models.CharField(max_length=40, blank=True)
    claimant_relationship = models.CharField(
        max_length=120,
        help_text="e.g., 'I am the account owner (I am alive)' or 'Spouse / Family member'",
    )
    details = models.TextField()
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.OPEN)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
