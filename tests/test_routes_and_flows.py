"""End-to-end route & workflow smoke tests across every Family, Visitor, and Staff screen."""
from __future__ import annotations

import zipfile
import io
import pytest
from django.core.management import call_command
from django.urls import reverse

from siteapp.accounts.models import User


@pytest.mark.django_db
def test_seed_demo_data_and_all_pages_render_cleanly(client):
    """Run seed_demo_data twice (idempotent) and verify every core page renders HTTP 200."""
    call_command("seed_demo_data")
    call_command("seed_demo_data")

    # Public routes
    for url in [
        reverse("home"),
        reverse("healthz"),
        reverse("policies"),
        reverse("memorials:discover"),
        reverse("memorials:detail", kwargs={"slug": "evelyn-pendelton-1946"}),
        reverse("memorials:print", kwargs={"slug": "evelyn-pendelton-1946"}),
        reverse("integrations:directory"),
        reverse("integrations:support_site"),
        reverse("stewardship:dispute"),
        reverse("accounts:login"),
        reverse("accounts:register"),
    ]:
        resp = client.get(url)
        assert resp.status_code == 200, f"Expected 200 on {url}, got {resp.status_code}"

    # Living owner (Arthur) routes
    arthur = User.objects.get(email="arthur@example.org")
    client.force_login(arthur)
    for url in [
        reverse("planning:dashboard"),
        reverse("planning:edit_plan"),
        reverse("planning:add_memory"),
        reverse("planning:wishes_wizard"),
        reverse("planning:download_worksheet"),
        reverse("memorials:owner_preview"),
        reverse("stewardship:manage"),
        reverse("accounts:profile"),
        reverse("accounts:grants"),
        reverse("events:contacts"),
        reverse("integrations:facebook_import"),
        reverse("integrations:contact_import"),
        reverse("integrations:status"),
    ]:
        resp = client.get(url)
        assert resp.status_code == 200, f"Expected 200 on {url}, got {resp.status_code}"

    # Verify ZIP archive export contains readable HTML and JSON
    export_resp = client.get(reverse("planning:export_archive"))
    assert export_resp.status_code == 200
    assert export_resp["Content-Type"] == "application/zip"
    with zipfile.ZipFile(io.BytesIO(export_resp.content)) as zf:
        names = set(zf.namelist())
        assert "my-plan-readable.html" in names
        assert "my-plan-data.json" in names

    # Steward (Clara) workspace renders cleanly while Arthur is living (hides private wishes!)
    clara = User.objects.get(email="clara@example.org")
    client.force_login(clara)
    ws_resp = client.get(reverse("stewardship:workspace", kwargs={"owner_person_id": arthur.person_id}))
    assert ws_resp.status_code == 200
    assert "Account owner is living" in ws_resp.content.decode()
    assert "green fireproof box" not in ws_resp.content.decode()

    # Staff reviewer (Hannah) is redirected to MFA first, then opens Staff Desk cleanly
    reviewer = User.objects.get(email="reviewer@example.org")
    client.force_login(reviewer)
    mfa_redirect = client.get(reverse("stewardship:staff_desk"))
    assert mfa_redirect.status_code == 302
    assert reverse("accounts:mfa") in mfa_redirect["Location"]
    client.post(reverse("accounts:mfa"), {"code": "482910"})
    desk_resp = client.get(reverse("stewardship:staff_desk"))
    assert desk_resp.status_code == 200
    assert "Verification" in desk_resp.content.decode()
