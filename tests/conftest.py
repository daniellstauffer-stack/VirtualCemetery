"""Shared pytest fixtures for fictional Virtual Cemetery families."""
from __future__ import annotations

import io
import pytest
from PIL import Image

from siteapp.accounts.models import User
from siteapp.planning.models import LifePlan


@pytest.fixture(autouse=True)
def isolated_storage(settings, tmp_path):
    """Route private media and case evidence into isolated temp directories per test."""
    settings.USE_GCS_STORAGE = False
    settings.MEDIA_ROOT = tmp_path / "media"
    settings.EVIDENCE_ROOT = tmp_path / "evidence"
    settings.CLOUD_TASKS_ENABLED = False
    settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
    settings.EMAIL_PROVIDER = "console"
    settings.LOCAL_AUTH_EMULATOR = True
    settings.STRIPE_WEBHOOK_SECRET = "whsec_test_secret_12345"
    settings.STRIPE_CURRENCY = "usd"


@pytest.fixture
def sample_jpeg_with_exif() -> bytes:
    """Generate a valid JPEG containing synthetic EXIF camera metadata for strip verification."""
    img = Image.new("RGB", (320, 240), color=(96, 128, 110))
    exif = img.getexif()
    exif[0x010F] = "SyntheticCameraMake"
    exif[0x013B] = "PrivateAuthorTag"
    buf = io.BytesIO()
    img.save(buf, format="JPEG", exif=exif.tobytes())
    return buf.getvalue()


@pytest.fixture
def fictional_family(db):
    """Create Arthur (owner), Clara (steward/organizer), Elena (visitor), and two Staff Reviewers."""
    arthur = User.objects.create_user(
        email="arthur.test@example.org",
        password="StrongPassword123!",
        display_name="Arthur Pendelton",
        email_verified=True,
        mfa_enabled=True,
    )
    clara = User.objects.create_user(
        email="clara.test@example.org",
        password="StrongPassword123!",
        display_name="Clara Pendelton",
        email_verified=True,
        mfa_enabled=True,
    )
    elena = User.objects.create_user(
        email="elena.test@example.org",
        password="StrongPassword123!",
        display_name="Elena Pendelton",
        email_verified=True,
    )
    stranger = User.objects.create_user(
        email="stranger@example.org",
        password="StrongPassword123!",
        display_name="Outside Visitor",
        email_verified=True,
    )
    reviewer1 = User.objects.create_user(
        email="reviewer1@example.org",
        password="StaffPassword123!",
        display_name="Hannah Brooks",
        email_verified=True,
        is_staff=True,
        is_verified_reviewer=True,
        mfa_enabled=True,
    )
    reviewer2 = User.objects.create_user(
        email="reviewer2@example.org",
        password="StaffPassword123!",
        display_name="David Kim",
        email_verified=True,
        is_staff=True,
        is_verified_reviewer=True,
        mfa_enabled=True,
    )
    plan = LifePlan.objects.create(
        owner=arthur,
        memorial_preferred_name="Arthur H. Pendelton",
        birth_year=1944,
        biography_draft="Cabinetmaker and weekend boatbuilder.",
        disposition_preference=LifePlan.DispositionChoice.GREEN_BURIAL,
        disposition_notes="SECRET_PRIVATE_WISH_GREEN_MEADOW_7741",
        service_wishes="SECRET_SERVICE_NOTE_SCHUBERT_TRIO",
        important_document_locations="SECRET_SAFE_COMBINATION_HINT",
        memorial_audience_ceiling=LifePlan.MemorialAudienceCeiling.INVITED_ONLY,
        allow_site_search=False,
    )
    return {
        "arthur": arthur,
        "clara": clara,
        "elena": elena,
        "stranger": stranger,
        "reviewer1": reviewer1,
        "reviewer2": reviewer2,
        "plan": plan,
    }
