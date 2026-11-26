"""Automated release-criteria tests mapped 1-to-1 to docs/product-requirements.md."""
from __future__ import annotations

import hashlib
import hmac
import io
import json
import time
from datetime import timedelta

import pytest
from django.core import mail
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from django.utils import timezone
from PIL import Image

from siteapp.events.models import FuneralContact, FuneralEvent, InvitationDelivery
from siteapp.integrations.importers import parse_contacts_csv_or_vcard, parse_facebook_export_json
from siteapp.integrations.models import SiteContribution
from siteapp.jobs.tasks import deliver_funeral_invitation, process_plan_memory_photo
from siteapp.memorials.models import (
    GuestbookEntry,
    Memorial,
    MemorialInvite,
    MemorialRelationship,
)
from siteapp.memorials.services import publish_memorial_snapshot
from siteapp.planning.models import PlanMemory
from siteapp.stewardship.models import DeathReport, StewardAssignment
from siteapp.stewardship.services import approve_death_report, reverse_death_report


def _verify_mfa(client, code="482910"):
    resp = client.post(reverse("accounts:mfa"), {"code": code})
    assert resp.status_code == 302


# =============================================================================
# Criterion 1: Strict Isolation Between Private Plan & Published Memorial + EXIF Stripping
# =============================================================================
@pytest.mark.django_db
def test_criterion_1_private_plan_isolation_and_exif_stripping(client, fictional_family, sample_jpeg_with_exif):
    arthur = fictional_family["arthur"]
    clara = fictional_family["clara"]
    elena = fictional_family["elena"]
    stranger = fictional_family["stranger"]
    reviewer1 = fictional_family["reviewer1"]
    plan = fictional_family["plan"]

    # Add one selected memorial photo (with EXIF!) and one strictly private photo + private guest list name
    selected_mem = PlanMemory.objects.create(
        plan=plan,
        title="Willow Lake Morning",
        story="Rowing out before sunrise.",
        alt_text="Wooden boat under willow trees",
        audience=PlanMemory.Audience.INVITED_MEMORIAL,
        owner_confirmed_rights=True,
        photo_original=SimpleUploadedFile("lake.jpg", sample_jpeg_with_exif, content_type="image/jpeg"),
    )
    assert process_plan_memory_photo(str(selected_mem.id)) is True
    selected_mem.refresh_from_db()

    # Verify EXIF metadata was stripped from the processed display copy
    with selected_mem.photo_display.open("rb") as fh:
        with Image.open(fh) as disp_img:
            assert len(disp_img.getexif()) == 0

    private_mem = PlanMemory.objects.create(
        plan=plan,
        title="SECRET_PRIVATE_DIARY_PHOTO",
        story="Never share this private story.",
        alt_text="Private diary scan",
        audience=PlanMemory.Audience.PRIVATE_ONLY,
        owner_confirmed_rights=True,
        photo_original=SimpleUploadedFile("secret.jpg", sample_jpeg_with_exif, content_type="image/jpeg"),
    )
    process_plan_memory_photo(str(private_mem.id))

    FuneralContact.objects.create(
        owner=arthur,
        full_name="SECRET_GUESTLIST_PERSON_991",
        email="secret.guest@example.org",
    )

    # Designate Clara as accepted steward & verify death
    StewardAssignment.objects.create(
        owner=arthur,
        invitee_name=clara.full_display_name,
        invitee_email=clara.email,
        steward_user=clara,
        status=StewardAssignment.Status.ACCEPTED,
        accepted_at=timezone.now(),
    )
    report = DeathReport.objects.create(
        subject_owner=arthur,
        submitted_by=clara,
        evidence_summary="Certified death record verified.",
        independent_evidence_checked=True,
        owner_challenge_sent_at=timezone.now(),
    )
    approve_death_report(report, reviewer1, "Independent evidence confirmed.")

    # Publish snapshot with BOTH IDs attempted — private_mem MUST be ignored by publisher!
    memorial = publish_memorial_snapshot(
        owner=arthur,
        steward=clara,
        selected_memory_ids=[str(selected_mem.id), str(private_mem.id)],
        chosen_audience=Memorial.Audience.PUBLIC,  # Owner ceiling is INVITED_ONLY -> must clamp!
        allow_site_search=True,
    )
    assert memorial.audience == Memorial.Audience.INVITED_ONLY
    assert memorial.allow_site_search is False
    assert memorial.published_memories.count() == 1
    pub_mem = memorial.published_memories.first()
    assert pub_mem.title == "Willow Lake Morning"

    # Mutating LifePlan afterward must NOT leak into the published memorial snapshot!
    plan.biography_draft = "MUTATED_PRIVATE_BIO_SHOULD_NOT_APPEAR"
    plan.save()

    # Uninvited stranger tries memorial page, search, direct plan image URL, and direct published image URL
    client.force_login(stranger)
    assert client.get(reverse("memorials:detail", kwargs={"slug": memorial.slug})).status_code == 404
    assert client.get(reverse("planning:memory_image", kwargs={"memory_id": private_mem.id})).status_code == 404
    assert client.get(reverse("planning:memory_image", kwargs={"memory_id": selected_mem.id})).status_code == 404
    assert client.get(
        reverse("memorials:memory_image", kwargs={"slug": memorial.slug, "memory_id": pub_mem.id})
    ).status_code == 404

    search_resp = client.get(reverse("memorials:discover"), {"q": "Arthur"})
    assert list(search_resp.context["page_obj"].object_list) == []
    assert memorial.slug not in search_resp.content.decode()
    assert "Arthur H. Pendelton" not in search_resp.content.decode()
    assert "SECRET_GUESTLIST_PERSON_991" not in search_resp.content.decode()

    # Invite Elena and redeem -> Elena sees ONLY the selected photo, NEVER private wishes or guest list
    invite = MemorialInvite.objects.create(
        memorial=memorial,
        invited_by=clara,
        intended_email=elena.email,
        intended_name=elena.full_display_name,
    )
    client.force_login(elena)
    redeem = client.get(reverse("memorials:redeem_invite", kwargs={"token": invite.token}))
    assert redeem.status_code == 302

    detail = client.get(reverse("memorials:detail", kwargs={"slug": memorial.slug}))
    assert detail.status_code == 200
    body = detail.content.decode()
    assert "Willow Lake Morning" in body
    assert "SECRET_PRIVATE_WISH_GREEN_MEADOW_7741" not in body
    assert "SECRET_PRIVATE_DIARY_PHOTO" not in body
    assert "SECRET_GUESTLIST_PERSON_991" not in body
    assert "MUTATED_PRIVATE_BIO_SHOULD_NOT_APPEAR" not in body
    assert detail["X-Robots-Tag"] == "noindex, nofollow, noarchive"

    # Elena can fetch the published photograph, but NOT the private plan photograph
    assert client.get(
        reverse("memorials:memory_image", kwargs={"slug": memorial.slug, "memory_id": pub_mem.id})
    ).status_code == 200
    assert client.get(reverse("planning:memory_image", kwargs={"memory_id": private_mem.id})).status_code == 404


# =============================================================================
# Criterion 2: Immediate Steward Revocation Invalidates Old Invites & Existing Sessions
# =============================================================================
@pytest.mark.django_db
def test_criterion_2_immediate_steward_revocation(client, fictional_family):
    arthur = fictional_family["arthur"]
    clara = fictional_family["clara"]

    assignment = StewardAssignment.objects.create(
        owner=arthur,
        invitee_name=clara.full_display_name,
        invitee_email=clara.email,
        role=StewardAssignment.Role.PRIMARY,
        status=StewardAssignment.Status.INVITED,
    )

    # Clara accepts via her signed-in session
    clara_client = client.__class__()
    clara_client.force_login(clara)
    resp = clara_client.post(
        reverse("stewardship:respond_invite", kwargs={"token": assignment.invite_token}),
        {"decision": "accept"},
    )
    assert resp.status_code == 302
    assert clara_client.get(
        reverse("stewardship:workspace", kwargs={"owner_person_id": arthur.person_id})
    ).status_code == 200

    # Arthur revokes Clara (requires MFA)
    arthur_client = client.__class__()
    arthur_client.force_login(arthur)
    _verify_mfa(arthur_client)
    rev_resp = arthur_client.post(reverse("stewardship:revoke", kwargs={"assignment_id": assignment.id}))
    assert rev_resp.status_code == 302

    # Clara's EXISTING signed-in session immediately fails to open workspace or submit a report
    assert clara_client.get(
        reverse("stewardship:workspace", kwargs={"owner_person_id": arthur.person_id})
    ).status_code == 404
    assert clara_client.get(
        reverse("stewardship:submit_report", kwargs={"owner_person_id": arthur.person_id})
    ).status_code == 404

    # Trying the old invitation link also fails (410 Gone)
    assert clara_client.get(
        reverse("stewardship:respond_invite", kwargs={"token": assignment.invite_token})
    ).status_code == 410


# =============================================================================
# Criterion 3: False Death Report, Public Dispute, Restricted Evidence, & Full Reversal Drill
# =============================================================================
@pytest.mark.django_db
def test_criterion_3_false_report_dispute_and_reversal_drill(client, fictional_family):
    arthur = fictional_family["arthur"]
    clara = fictional_family["clara"]
    elena = fictional_family["elena"]
    reviewer1 = fictional_family["reviewer1"]

    StewardAssignment.objects.create(
        owner=arthur,
        invitee_name=clara.full_display_name,
        invitee_email=clara.email,
        steward_user=clara,
        can_organize_funeral=True,
        status=StewardAssignment.Status.ACCEPTED,
        accepted_at=timezone.now(),
    )
    c1 = FuneralContact.objects.create(owner=arthur, full_name="Elena", email=elena.email)
    c2 = FuneralContact.objects.create(owner=arthur, full_name="Thomas", email="thomas@example.org")

    # 1. File a death report -> MUST send zero funeral mail and NOT alter public pages
    clara_client = client.__class__()
    clara_client.force_login(clara)
    evidence = SimpleUploadedFile("notice.pdf", b"%PDF-1.4 fake test pdf", content_type="application/pdf")
    post_resp = clara_client.post(
        reverse("stewardship:submit_report", kwargs={"owner_person_id": arthur.person_id}),
        {
            "submitter_relationship": "Daughter",
            "evidence_summary": "Mistaken report filed in rehearsal.",
            "evidence_file": evidence,
        },
    )
    assert post_resp.status_code == 302
    assert len(mail.outbox) == 0
    arthur.refresh_from_db()
    assert arthur.is_deceased_verified is False

    report = DeathReport.objects.get(subject_owner=arthur)

    # Non-staff steward cannot download staff case evidence
    assert clara_client.get(reverse("stewardship:staff_evidence", kwargs={"report_id": report.id})).status_code == 404

    # 2. Living owner challenges WITHOUT signing in -> case automatically pauses for second reviewer!
    anon_client = client.__class__()
    dispute_resp = anon_client.post(
        reverse("stewardship:dispute"),
        {
            "subject_email_or_name": arthur.email,
            "claimant_name": "Arthur Pendelton",
            "claimant_email": arthur.email,
            "claimant_relationship": "I am the account owner and I am alive",
            "details": "Please pause immediately, this report is a mistake.",
        },
    )
    assert dispute_resp.status_code == 302
    report.refresh_from_db()
    assert report.status == DeathReport.Status.CONFLICT_PAUSED

    # 3. Rehearse reversing an approved case (with published memorial, invite, 1 sent + 1 queued email)
    report2 = DeathReport.objects.create(
        subject_owner=arthur,
        submitted_by=clara,
        evidence_summary="Reversal rehearsal case.",
        independent_evidence_checked=True,
        owner_challenge_sent_at=timezone.now(),
    )
    approve_death_report(report2, reviewer1, "Approved for reversal drill.")
    memorial = publish_memorial_snapshot(
        owner=arthur,
        steward=clara,
        selected_memory_ids=[],
        chosen_audience=Memorial.Audience.INVITED_ONLY,
        allow_site_search=False,
    )
    inv = MemorialInvite.objects.create(memorial=memorial, invited_by=clara, intended_email=elena.email)
    ev = FuneralEvent.objects.create(
        owner=arthur,
        organizer=clara,
        title="Service Rehearsal",
        status=FuneralEvent.Status.CONFIRMED,
    )
    sent_delivery = InvitationDelivery.objects.create(
        event=ev,
        event_version=1,
        contact=c1,
        recipient_email=c1.email,
        recipient_name=c1.full_name,
        idempotency_key=InvitationDelivery.build_idempotency_key(ev, c1),
        status=InvitationDelivery.Status.SENT,
        sent_at=timezone.now(),
    )
    queued_delivery = InvitationDelivery.objects.create(
        event=ev,
        event_version=1,
        contact=c2,
        recipient_email=c2.email,
        recipient_name=c2.full_name,
        idempotency_key=InvitationDelivery.build_idempotency_key(ev, c2),
        status=InvitationDelivery.Status.QUEUED,
    )

    summary = reverse_death_report(report2, reviewer1, "Owner confirmed alive via phone & video check.")
    arthur.refresh_from_db()
    memorial.refresh_from_db()
    inv.refresh_from_db()
    queued_delivery.refresh_from_db()
    report2.refresh_from_db()

    assert arthur.is_deceased_verified is False
    assert arthur.is_active is True
    assert memorial.status == Memorial.Status.SUSPENDED
    assert inv.revoked_at is not None
    assert queued_delivery.status == InvitationDelivery.Status.CANCELLED
    assert summary["already_delivered_count"] == 1
    assert report2.erroneous_notices_snapshot[0]["recipient_email"] == c1.email
    assert sent_delivery.recipient_email == c1.email


# =============================================================================
# Criterion 4: Consensual Relationships & Visibility Loss on Revocation or Narrowed Privacy
# =============================================================================
@pytest.mark.django_db
def test_criterion_4_relationship_consent_and_privacy_revocation(client, fictional_family):
    clara = fictional_family["clara"]
    stranger = fictional_family["stranger"]

    m1 = Memorial.objects.create(
        full_name="Evelyn Pendelton",
        slug="evelyn-rel-test",
        status=Memorial.Status.PUBLISHED,
        audience=Memorial.Audience.PUBLIC,
        allow_site_search=True,
        is_family_created=True,
        published_by=clara,
    )
    m2 = Memorial.objects.create(
        full_name="Samuel Mercer",
        slug="samuel-rel-test",
        status=Memorial.Status.PUBLISHED,
        audience=Memorial.Audience.PUBLIC,
        allow_site_search=True,
        is_family_created=True,
        published_by=clara,
    )

    rel = MemorialRelationship.objects.create(
        from_memorial=m1,
        to_memorial=m2,
        label_from_to="Lifelong friend of",
        label_to_from="Lifelong friend of",
        proposed_by=clara,
        from_approved=True,
        to_approved=False,
        status=MemorialRelationship.Status.PROPOSED,
    )

    # Before both sides agree, visitor must NOT see the relationship
    client.force_login(stranger)
    resp = client.get(reverse("memorials:detail", kwargs={"slug": m1.slug}))
    assert "Samuel Mercer" not in resp.content.decode()

    # Once target side accepts, visitor sees it (both endpoints are public)
    rel.accept_target_side()
    resp = client.get(reverse("memorials:detail", kwargs={"slug": m1.slug}))
    assert "Samuel Mercer" in resp.content.decode()

    # Make m2 invited-only -> stranger immediately loses the relationship link on m1 AND m2 vanishes from search!
    m2.audience = Memorial.Audience.INVITED_ONLY
    m2.save()
    resp = client.get(reverse("memorials:detail", kwargs={"slug": m1.slug}))
    assert "Samuel Mercer" not in resp.content.decode()
    search_resp = client.get(reverse("memorials:discover"), {"q": "Samuel Mercer"})
    assert list(search_resp.context["page_obj"].object_list) == []
    assert m2.slug not in search_resp.content.decode()

    # Restore m2 public, then withdraw consent -> relationship vanishes immediately too
    m2.audience = Memorial.Audience.PUBLIC
    m2.save()
    rel.withdraw()
    resp = client.get(reverse("memorials:detail", kwargs={"slug": m1.slug}))
    assert "Samuel Mercer" not in resp.content.decode()


# =============================================================================
# Criterion 5: Idempotency (Duplicate Import, Retry Send, Reconciliation, Replayed Payment Webhook)
# =============================================================================
@pytest.mark.django_db
def test_criterion_5_idempotency_and_reconciliation(client, fictional_family):
    arthur = fictional_family["arthur"]
    clara = fictional_family["clara"]
    reviewer1 = fictional_family["reviewer1"]

    # 1. Import the same contact twice via CSV -> 1 recipient, duplicate flagged
    csv_data = "name,email,relationship\nNora Lindholm,nora@example.org,Neighbor\nNora Again,NORA@example.org,Neighbor\n"
    parsed = parse_contacts_csv_or_vcard(csv_data, "contacts.csv", existing_emails=set())
    assert len(parsed) == 2
    assert parsed[0]["is_duplicate"] is False
    assert parsed[1]["is_duplicate"] is True

    client.force_login(arthur)
    f1 = SimpleUploadedFile("contacts.csv", csv_data.encode("utf-8"), content_type="text/csv")
    client.post(reverse("integrations:contact_import"), {"step": "upload", "contacts_file": f1})
    client.post(
        reverse("integrations:contact_import"),
        {"step": "confirm", "selected_emails": ["nora@example.org", "nora@example.org"]},
    )
    assert FuneralContact.objects.filter(owner=arthur, email="nora@example.org").count() == 1

    # 2. Retry sending funeral invitations -> strictly 1 delivery request per (event, version, contact)
    StewardAssignment.objects.create(
        owner=arthur,
        invitee_name=clara.full_display_name,
        invitee_email=clara.email,
        steward_user=clara,
        can_organize_funeral=True,
        status=StewardAssignment.Status.ACCEPTED,
        accepted_at=timezone.now(),
    )
    report = DeathReport.objects.create(
        subject_owner=arthur,
        submitted_by=clara,
        evidence_summary="Verified.",
        independent_evidence_checked=True,
        owner_challenge_sent_at=timezone.now(),
    )
    approve_death_report(report, reviewer1, "Confirmed.")

    ev = FuneralEvent.objects.create(owner=arthur, organizer=clara, title="Gathering")
    clara_client = client.__class__()
    clara_client.force_login(clara)
    clara_client.post(reverse("events:send_invitations", kwargs={"event_id": ev.id}))
    clara_client.post(reverse("events:send_invitations", kwargs={"event_id": ev.id}))  # Retry!
    assert InvitationDelivery.objects.filter(event=ev).count() == 1
    assert len(mail.outbox) == 1

    # 3. Ambiguous timeout -> moves to NEEDS_RECONCILIATION and refuses blind retry
    c_ambig = FuneralContact.objects.create(owner=arthur, full_name="Sam", email="sam.ambig@example.org")
    d_ambig = InvitationDelivery.objects.create(
        event=ev,
        event_version=ev.version,
        contact=c_ambig,
        recipient_email=c_ambig.email,
        recipient_name=c_ambig.full_name,
        idempotency_key=InvitationDelivery.build_idempotency_key(ev, c_ambig),
        status=InvitationDelivery.Status.QUEUED,
    )
    assert deliver_funeral_invitation(str(d_ambig.id), simulate_timeout=True) == InvitationDelivery.Status.NEEDS_RECONCILIATION
    # Blind retry MUST NOT send while in reconciliation state!
    assert deliver_funeral_invitation(str(d_ambig.id), simulate_timeout=False) == InvitationDelivery.Status.NEEDS_RECONCILIATION
    assert len(mail.outbox) == 1

    # 4. Replay Stripe payment webhook notification -> strictly 1 SiteContribution recorded!
    payload = json.dumps(
        {
            "id": "evt_test_replay_001",
            "type": "checkout.session.completed",
            "data": {
                "object": {
                    "id": "cs_test_session_001",
                    "amount_total": 2500,
                    "currency": "usd",
                    "customer_email": "supporter@example.org",
                }
            },
        }
    ).encode("utf-8")
    ts = str(int(time.time()))
    sig = hmac.new(b"whsec_test_secret_12345", f"{ts}.".encode() + payload, hashlib.sha256).hexdigest()
    headers = {"HTTP_STRIPE_SIGNATURE": f"t={ts},v1={sig}"}

    r1 = client.post(reverse("integrations:stripe_webhook"), data=payload, content_type="application/json", **headers)
    r2 = client.post(reverse("integrations:stripe_webhook"), data=payload, content_type="application/json", **headers)
    assert r1.status_code == 200 and r1.json()["recorded_new"] is True
    assert r2.status_code == 200 and r2.json()["recorded_new"] is False
    assert SiteContribution.objects.count() == 1

    # 5. Facebook archive parser rejects private message threads and excludes other people's posts
    with pytest.raises(ValueError):
        parse_facebook_export_json(b'{"participants": ["A", "B"], "messages": []}', set())
    fb_posts = json.dumps(
        [
            {"id": "p1", "timestamp": 1700000000, "data": [{"post": "My garden rose story"}]},
            {"id": "p2", "is_other_person_post": True, "data": [{"post": "Someone else's post"}]},
        ]
    ).encode("utf-8")
    parsed_fb = parse_facebook_export_json(fb_posts, set())
    assert len(parsed_fb) == 1
    assert parsed_fb[0]["external_id"] == "fb:p1"


# =============================================================================
# Criterion 6: Keyboard & Screen-Reader Accessibility Markup + Guestbook Moderation
# =============================================================================
@pytest.mark.django_db
def test_criterion_6_accessibility_landmarks_and_guestbook_moderation(client, fictional_family):
    arthur = fictional_family["arthur"]
    clara = fictional_family["clara"]
    elena = fictional_family["elena"]

    client.force_login(arthur)
    form_pages = {"planning:add_memory", "stewardship:manage", "planning:wishes_wizard"}
    for url_name in ("planning:dashboard", "planning:add_memory", "stewardship:manage", "planning:wishes_wizard"):
        resp = client.get(reverse(url_name))
        assert resp.status_code == 200
        html = resp.content.decode()
        assert 'href="#main-content"' in html
        assert '<main id="main-content"' in html
        assert html.count("<h1") == 1
        if url_name in form_pages:
            assert "<label for=" in html

    # Guestbook pending notes visible ONLY to author & steward, never to other visitors
    mem = Memorial.objects.create(
        full_name="Evelyn Pendelton",
        slug="evelyn-gb-test",
        status=Memorial.Status.PUBLISHED,
        audience=Memorial.Audience.PUBLIC,
        guestbook_requires_approval=True,
        is_family_created=True,
        published_by=clara,
    )
    client.force_login(elena)
    client.post(
        reverse("memorials:add_guestbook", kwargs={"slug": mem.slug}),
        {"flower": GuestbookEntry.FlowerChoice.WHITE_LILY, "message": "PENDING_NOTE_FOR_MODERATION"},
    )
    # Author sees their own pending note
    assert "PENDING_NOTE_FOR_MODERATION" in client.get(reverse("memorials:detail", kwargs={"slug": mem.slug})).content.decode()

    # Anonymous / other visitor must NOT see pending note until steward approves
    anon = client.__class__()
    assert "PENDING_NOTE_FOR_MODERATION" not in anon.get(reverse("memorials:detail", kwargs={"slug": mem.slug})).content.decode()

    # Steward approves -> now visible to visitors
    entry = GuestbookEntry.objects.get(memorial=mem)
    client.force_login(clara)
    client.post(
        reverse("memorials:moderate_guestbook", kwargs={"slug": mem.slug, "entry_id": entry.id}),
        {"action": "approve"},
    )
    assert "PENDING_NOTE_FOR_MODERATION" in anon.get(reverse("memorials:detail", kwargs={"slug": mem.slug})).content.decode()
