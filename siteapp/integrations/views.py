"""Views for Facebook guided archive import, CSV/vCard contact import, local directory, voluntary support, and provider placeholders."""
from __future__ import annotations

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.http import HttpResponseBadRequest, HttpResponseForbidden, JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from siteapp.accounts.models import record_audit
from siteapp.events.models import FuneralContact
from siteapp.planning.models import PlanMemory
from siteapp.planning.views import get_or_create_plan

from .importers import parse_contacts_csv_or_vcard, parse_facebook_export_json
from .models import DirectoryProvider, SiteContribution
from .payments import create_checkout_session, process_stripe_webhook

# Official licensing directories shown even in unrated or sparse areas
OFFICIAL_LICENSING_LINKS = [
    {
        "title": "Oregon State Bar — Lawyer Directory & Discipline Lookup",
        "category": "Estate-planning attorneys",
        "url": "https://www.osbar.org/members/membersearch_start.asp",
        "description": "Verify active bar license status, practice areas, and disciplinary history in Oregon.",
    },
    {
        "title": "Oregon Mortuary and Cemetery Board — Facility & License Lookup",
        "category": "Funeral homes & crematories",
        "url": "https://www.oregon.gov/omcb/pages/index.aspx",
        "description": "Verify state licensing and inspection standing for Oregon funeral establishments and cemeteries.",
    },
    {
        "title": "National Academy of Elder Law Attorneys (NAELA) Directory",
        "category": "Estate & elder-law counsel",
        "url": "https://www.naela.org/findlawyer",
        "description": "National search for attorneys focusing on elder law and special-needs estate planning.",
    },
]


@login_required
def facebook_import_view(request):
    """Guided import from a user-downloaded Facebook JSON archive + Meta integration status."""
    plan = get_or_create_plan(request.user)
    existing_ids = set(
        plan.memories.exclude(source_external_id="").values_list("source_external_id", flat=True)
    )
    preview_items = request.session.get("fb_import_preview", [])

    if request.method == "POST":
        step = request.POST.get("step", "upload")
        if step == "cancel":
            request.session.pop("fb_import_preview", None)
            messages.info(request, "Facebook import cancelled. Nothing was saved and no archive was kept.")
            return redirect("integrations:facebook_import")

        if step == "upload":
            uploaded = request.FILES.get("archive_file")
            if not uploaded:
                messages.error(request, "Please select a Facebook JSON export file to preview.")
            elif uploaded.size > 5 * 1024 * 1024:
                messages.error(request, "Please upload a JSON export file under 5 MB.")
            else:
                try:
                    raw = uploaded.read()
                    preview_items = parse_facebook_export_json(raw, existing_ids)
                    request.session["fb_import_preview"] = preview_items
                    if not preview_items:
                        messages.info(request, "No importable personal posts were found in that file.")
                except ValueError as exc:
                    messages.error(request, str(exc))
                except Exception:
                    messages.error(request, "Could not read that file as a valid JSON export.")
            return redirect("integrations:facebook_import")

        if step == "confirm":
            if request.POST.get("confirm_ownership") != "yes":
                messages.error(
                    request,
                    "Please confirm that you own these stories/photos or have permission to save them.",
                )
                return redirect("integrations:facebook_import")

            selected_ids = set(request.POST.getlist("selected_items"))
            audience = request.POST.get("default_audience", PlanMemory.Audience.PRIVATE_ONLY)
            if audience not in dict(PlanMemory.Audience.choices):
                audience = PlanMemory.Audience.PRIVATE_ONLY

            saved_count = 0
            for item in preview_items:
                if item["external_id"] not in selected_ids:
                    continue
                if item["external_id"] in existing_ids:
                    continue
                PlanMemory.objects.create(
                    plan=plan,
                    title=item["title"],
                    year_taken=item["year_taken"],
                    story=item["story"],
                    alt_text=f"Imported story: {item['title']}",
                    audience=audience,
                    owner_confirmed_rights=True,
                    source_label="Facebook archive import",
                    source_external_id=item["external_id"],
                )
                existing_ids.add(item["external_id"])
                saved_count += 1

            # Immediately discard temporary preview from session
            request.session.pop("fb_import_preview", None)
            record_audit(
                action="import.facebook_archive",
                summary=f"Imported {saved_count} selected item(s) from user-supplied Facebook archive.",
                actor=request.user,
                subject_person_id=request.user.person_id,
            )
            messages.success(
                request,
                f"Imported {saved_count} selected memory item(s) into My Plan. Temporary preview discarded.",
            )
            return redirect("planning:dashboard")

    return render(
        request,
        "integrations/facebook_import.html",
        {
            "preview_items": preview_items,
            "facebook_login_enabled": settings.FACEBOOK_LOGIN_ENABLED,
            "facebook_app_id": settings.FACEBOOK_APP_ID,
            "facebook_api_version": settings.FACEBOOK_GRAPH_API_VERSION,
        },
    )


@login_required
def contact_import_view(request):
    """Guided CSV / vCard import into private funeral contacts with duplicate preview & cancel."""
    existing_emails = set(
        FuneralContact.objects.filter(owner=request.user).values_list("email", flat=True)
    )
    preview_contacts = request.session.get("contact_import_preview", [])

    if request.method == "POST":
        step = request.POST.get("step", "upload")
        if step == "cancel":
            request.session.pop("contact_import_preview", None)
            messages.info(request, "Contact import cancelled. No addresses were saved.")
            return redirect("integrations:contact_import")

        if step == "upload":
            uploaded = request.FILES.get("contacts_file")
            if not uploaded:
                messages.error(request, "Please select a CSV or vCard (.vcf) file.")
            else:
                try:
                    raw_text = uploaded.read().decode("utf-8-sig", errors="replace")
                    preview_contacts = parse_contacts_csv_or_vcard(
                        raw_text, uploaded.name, existing_emails
                    )
                    request.session["contact_import_preview"] = preview_contacts
                    if not preview_contacts:
                        messages.warning(request, "No valid email contacts were found in that file.")
                except Exception:
                    messages.error(request, "Unable to parse that contact file.")
            return redirect("integrations:contact_import")

        if step == "confirm":
            selected_emails = {e.lower() for e in request.POST.getlist("selected_emails")}
            added = 0
            duplicates = 0
            for c in preview_contacts:
                if c["email"] not in selected_emails:
                    continue
                _, created = FuneralContact.objects.get_or_create(
                    owner=request.user,
                    email=c["email"],
                    defaults={
                        "full_name": c["full_name"],
                        "relationship": c["relationship"],
                        "source": "CSV/vCard import",
                    },
                )
                if created:
                    added += 1
                else:
                    duplicates += 1

            request.session.pop("contact_import_preview", None)
            messages.success(
                request,
                f"Saved {added} contact(s) to your private funeral list ({duplicates} duplicate(s) skipped). "
                "Importing never sends invitations automatically.",
            )
            return redirect("events:contacts")

    return render(
        request,
        "integrations/contact_import.html",
        {
            "preview_contacts": preview_contacts,
            "google_people_enabled": settings.GOOGLE_PEOPLE_IMPORT_ENABLED,
            "google_client_id": settings.GOOGLE_OAUTH_CLIENT_ID,
            "ms_graph_enabled": settings.MICROSOFT_GRAPH_IMPORT_ENABLED,
            "ms_client_id": settings.MICROSOFT_CLIENT_ID,
        },
    )


def directory_view(request):
    """Local professional directory for funeral homes and estate-planning attorneys."""
    location = (request.GET.get("location") or "").strip()
    category = (request.GET.get("category") or "").strip()
    sort_by = request.GET.get("sort") or "rating"

    qs = DirectoryProvider.objects.all()
    if category in dict(DirectoryProvider.Category.choices):
        qs = qs.filter(category=category)
    if location:
        qs = qs.filter(
            Q(city__icontains=location)
            | Q(postal_code__icontains=location)
            | Q(state__icontains=location)
        )

    if sort_by == "name":
        qs = qs.order_by("name")
        sort_explanation = "Sorted alphabetically by provider name (A–Z). No paid placements are boosted."
    else:
        qs = qs.order_by("-rating", "-review_count", "name")
        sort_explanation = (
            "Sorted by public rating and number of reviews from the cited source, then alphabetically. "
            "Any paid placement would be explicitly labeled and never hides licensed providers."
        )

    return render(
        request,
        "integrations/directory.html",
        {
            "providers": qs,
            "location": location,
            "category": category,
            "sort_by": sort_by,
            "sort_explanation": sort_explanation,
            "licensing_links": OFFICIAL_LICENSING_LINKS,
            "google_places_enabled": settings.GOOGLE_PLACES_ENABLED,
        },
    )


def support_site_view(request):
    """Optional voluntary one-time contribution page via Stripe Hosted Checkout."""
    checkout_feedback = None
    if request.method == "POST":
        try:
            dollars = float(request.POST.get("amount_dollars", "15"))
            amount_cents = int(round(dollars * 100))
            result = create_checkout_session(
                amount_cents=amount_cents,
                user=request.user,
                success_url=request.build_absolute_uri(reverse("integrations:support_site")) + "?thanks=1",
                cancel_url=request.build_absolute_uri(reverse("integrations:support_site")),
            )
            if result["mode"] == "live":
                return redirect(result["checkout_url"])
            checkout_feedback = result["message"]
        except ValueError as exc:
            messages.error(request, str(exc))

    return render(
        request,
        "integrations/support_site.html",
        {
            "thanks": request.GET.get("thanks") == "1",
            "checkout_feedback": checkout_feedback,
            "payee_name": settings.STRIPE_PAYEE_LEGAL_NAME,
            "currency": settings.STRIPE_CURRENCY.upper(),
            "refund_contact": settings.SUPPORT_EMAIL,
            "tax_status": settings.STRIPE_TAX_DEDUCTIBLE_STATUS,
            "stripe_enabled": settings.STRIPE_ENABLED,
        },
    )


@csrf_exempt
@require_POST
def stripe_webhook_view(request):
    """Signed, idempotent Stripe webhook endpoint."""
    sig_header = request.headers.get("Stripe-Signature", "")
    try:
        contrib, recorded = process_stripe_webhook(request.body, sig_header)
        return JsonResponse(
            {
                "received": True,
                "recorded_new": recorded,
                "contribution_id": str(contrib.id) if contrib else None,
            }
        )
    except PermissionError:
        return HttpResponseForbidden("Invalid signature.")
    except ValueError as exc:
        return HttpResponseBadRequest(str(exc))


@login_required
def integrations_status_view(request):
    """Transparent view of configured service adapters & placeholders (helpful during pilot setup)."""
    def _is_placeholder(val: str) -> bool:
        return (not val) or ("placeholder" in val.lower()) or ("replace" in val.lower())

    services = [
        {
            "name": "Google Cloud Project & Private Storage",
            "configured": settings.USE_GCS_STORAGE and not _is_placeholder(settings.GCP_PROJECT_ID),
            "env_keys": "GCP_PROJECT_ID, USE_GCS_STORAGE, GCP_MEDIA_BUCKET, GCP_EVIDENCE_BUCKET",
            "notes": "Uses private local filesystem storage in dev; private GCS buckets with lifecycle purge in staging/prod.",
        },
        {
            "name": "Google Cloud Identity Platform (Auth & MFA)",
            "configured": (not settings.LOCAL_AUTH_EMULATOR) and not _is_placeholder(settings.GCP_IDENTITY_PLATFORM_API_KEY),
            "env_keys": "LOCAL_AUTH_EMULATOR, GCP_IDENTITY_PLATFORM_PROJECT_ID, GCP_IDENTITY_PLATFORM_API_KEY",
            "notes": "Local auth emulator active for development and family pilot rehearsals.",
        },
        {
            "name": "Google Cloud Tasks (Background Worker)",
            "configured": settings.CLOUD_TASKS_ENABLED and not _is_placeholder(settings.WORKER_BASE_URL),
            "env_keys": "CLOUD_TASKS_ENABLED, GCP_TASKS_QUEUE_NAME, WORKER_BASE_URL, WORKER_OIDC_SERVICE_ACCOUNT",
            "notes": "Runs worker handlers inline locally; dispatches authenticated OIDC tasks on Cloud Run.",
        },
        {
            "name": "Postmark Transactional Email",
            "configured": settings.EMAIL_PROVIDER == "postmark" and not _is_placeholder(settings.POSTMARK_SERVER_TOKEN),
            "env_keys": "EMAIL_PROVIDER, POSTMARK_SERVER_TOKEN, POSTMARK_MESSAGE_STREAM, EMAIL_FROM_ADDRESS",
            "notes": f"Currently using '{settings.EMAIL_PROVIDER}' backend (console or Mailpit SMTP locally).",
        },
        {
            "name": "Facebook / Meta (Login & Future Graph API)",
            "configured": settings.FACEBOOK_LOGIN_ENABLED and not _is_placeholder(settings.FACEBOOK_APP_ID),
            "env_keys": "FACEBOOK_LOGIN_ENABLED, FACEBOOK_APP_ID, FACEBOOK_APP_SECRET",
            "notes": "Guided Facebook JSON archive import works today without Meta App Review.",
        },
        {
            "name": "Google People & Microsoft Graph Contacts",
            "configured": settings.GOOGLE_PEOPLE_IMPORT_ENABLED or settings.MICROSOFT_GRAPH_IMPORT_ENABLED,
            "env_keys": "GOOGLE_OAUTH_CLIENT_ID, MICROSOFT_CLIENT_ID",
            "notes": "Manual entry and CSV/vCard import work today; OAuth address-book sync gated until provider verification.",
        },
        {
            "name": "Google Places API (Directory Expansion)",
            "configured": settings.GOOGLE_PLACES_ENABLED and not _is_placeholder(settings.GOOGLE_PLACES_API_KEY),
            "env_keys": "GOOGLE_PLACES_ENABLED, GOOGLE_PLACES_API_KEY, GOOGLE_PLACES_DAILY_QUOTA",
            "notes": "Pilot uses curated regional providers and official state licensing directories.",
        },
        {
            "name": "Stripe Hosted Checkout (Voluntary Support)",
            "configured": settings.STRIPE_ENABLED and not _is_placeholder(settings.STRIPE_SECRET_KEY),
            "env_keys": "STRIPE_ENABLED, STRIPE_PUBLISHABLE_KEY, STRIPE_SECRET_KEY, STRIPE_WEBHOOK_SECRET",
            "notes": "Voluntary support only — zero effect on memorial access.",
        },
    ]
    return render(request, "integrations/status.html", {"services": services})
