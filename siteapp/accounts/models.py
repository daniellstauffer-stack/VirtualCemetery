"""User identity, stable person IDs, per-record access grants, and audit logs."""
from __future__ import annotations

import uuid
from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db import models
from django.utils import timezone


class UserManager(BaseUserManager):
    use_in_migrations = True

    def _create_user(self, email: str, password: str | None, **extra_fields):
        if not email:
            raise ValueError("An email address is required.")
        email = self.normalize_email(email).lower()
        username = extra_fields.pop("username", None) or email
        user = self.model(email=email, username=username, **extra_fields)
        if password:
            user.set_password(password)
        else:
            user.set_unusable_password()
        user.save(using=self._db)
        return user

    def create_user(self, email: str, password: str | None = None, **extra_fields):
        extra_fields.setdefault("is_staff", False)
        extra_fields.setdefault("is_superuser", False)
        return self._create_user(email, password, **extra_fields)

    def create_superuser(self, email: str, password: str, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("is_verified_reviewer", True)
        extra_fields.setdefault("email_verified", True)
        extra_fields.setdefault("mfa_enabled", True)
        return self._create_user(email, password, **extra_fields)


class User(AbstractUser):
    """Account with a stable internal person_id decoupled from name/email/provider."""

    person_id = models.UUIDField(
        default=uuid.uuid4,
        unique=True,
        editable=False,
        db_index=True,
        help_text="Stable internal identifier so name, email, or provider changes never duplicate a memorial.",
    )
    email = models.EmailField(unique=True)
    display_name = models.CharField(max_length=150, blank=True)
    email_verified = models.BooleanField(default=False)
    verified_phone_hint = models.CharField(
        max_length=40,
        blank=True,
        help_text="Optional verified recovery phone or alternate contact channel used for death-report challenges.",
    )
    jurisdiction = models.CharField(max_length=120, default="Oregon, United States")

    # External identity provider links (optional / configured via env)
    identity_platform_uid = models.CharField(max_length=128, blank=True, null=True, unique=True)
    facebook_uid = models.CharField(max_length=128, blank=True, null=True, unique=True)

    # Staff verification role (separate from family guestbook moderation)
    is_verified_reviewer = models.BooleanField(
        default=False,
        help_text="Authorized to review death reports and disputes on the restricted staff desk.",
    )
    mfa_enabled = models.BooleanField(
        default=False,
        help_text="Whether multi-factor verification is enrolled (required for staff reviewers and high-impact actions).",
    )
    mfa_demo_code = models.CharField(
        max_length=12,
        default="482910",
        help_text="Local-emulator-only 6-digit MFA code; in production, Google Cloud Identity Platform enforces MFA.",
    )

    # Death verification status (set only via approved DeathReport, reversible by appeal)
    is_deceased_verified = models.BooleanField(default=False)
    death_verified_at = models.DateTimeField(null=True, blank=True)

    # Accessibility preference
    preferred_text_scale = models.CharField(
        max_length=12,
        choices=[("normal", "Standard"), ("large", "Large"), ("xlarge", "Extra Large")],
        default="normal",
    )

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []

    objects = UserManager()

    @property
    def full_display_name(self) -> str:
        if self.display_name.strip():
            return self.display_name.strip()
        full = self.get_full_name().strip()
        return full or self.email.split("@")[0]

    def __str__(self) -> str:
        return f"{self.full_display_name} <{self.email}>"


class AccessGrant(models.Model):
    """Explicit grant by an account owner allowing a named recipient to view
    specific private planning sections (e.g. funeral instructions or contacts)
    either while alive or only after a verified death.
    """

    class Scope(models.TextChoices):
        FUNERAL_INSTRUCTIONS = "funeral_instructions", "Funeral & service instructions"
        CONTACT_LIST = "contact_list", "Funeral contact list"
        DOCUMENT_LOCATIONS = "document_locations", "Location of important papers"
        BURIAL_WISHES = "burial_wishes", "Burial or cremation preferences"

    class ReleaseTiming(models.TextChoices):
        WHILE_ALIVE = "while_alive", "Available now (while I am alive)"
        AFTER_VERIFIED_DEATH = "after_verified_death", "Only after my death is verified"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name="outgoing_grants")
    recipient_email = models.EmailField()
    recipient_user = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="incoming_grants",
    )
    scope = models.CharField(max_length=40, choices=Scope.choices)
    release_timing = models.CharField(
        max_length=30,
        choices=ReleaseTiming.choices,
        default=ReleaseTiming.AFTER_VERIFIED_DEATH,
    )
    note_to_recipient = models.CharField(max_length=240, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    revoked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["owner", "revoked_at"]),
            models.Index(fields=["recipient_email", "revoked_at"]),
        ]

    @property
    def is_active(self) -> bool:
        return self.revoked_at is None

    def is_currently_accessible_by(self, user: User | None) -> bool:
        """Recheck live grant validity, identity match, and timing rules."""
        if not user or not user.is_authenticated or self.revoked_at is not None:
            return False
        matches_recipient = (
            (self.recipient_user_id and self.recipient_user_id == user.id)
            or (self.recipient_email.lower() == user.email.lower() and user.email_verified)
        )
        if not matches_recipient:
            return False
        if self.release_timing == self.ReleaseTiming.WHILE_ALIVE:
            return True
        return bool(self.owner.is_deceased_verified)

    def revoke(self):
        if self.revoked_at is None:
            self.revoked_at = timezone.now()
            self.save(update_fields=["revoked_at"])


class AuditEvent(models.Model):
    """Append-only audit history of security, permission, and review actions.

    Never stores private planning text, contact lists, access tokens, or raw evidence.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    actor = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="audit_events_performed",
    )
    subject_person_id = models.UUIDField(null=True, blank=True, db_index=True)
    action = models.CharField(max_length=80, db_index=True)
    target_type = models.CharField(max_length=60, blank=True)
    target_id = models.CharField(max_length=80, blank=True)
    summary = models.CharField(max_length=300)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"[{self.created_at:%Y-%m-%d %H:%M}] {self.action}: {self.summary}"


def record_audit(
    *,
    action: str,
    summary: str,
    actor: User | None = None,
    subject_person_id=None,
    target_type: str = "",
    target_id: str = "",
) -> AuditEvent:
    """Create a scrubbed operational audit event."""
    return AuditEvent.objects.create(
        actor=actor if (actor and getattr(actor, "is_authenticated", False)) else None,
        subject_person_id=subject_person_id,
        action=action,
        target_type=target_type,
        target_id=str(target_id) if target_id else "",
        summary=summary[:300],
    )
