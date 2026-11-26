"""Views for My Plan workspace, memories, authenticated media serving, worksheet wizard, and portability exports."""
from __future__ import annotations

import io
import json
import zipfile
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import FileResponse, Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.utils import timezone
from django.views.decorators.http import require_POST

from siteapp.accounts.models import AccessGrant, record_audit
from siteapp.jobs.tasks import enqueue_photo_processing
from siteapp.stewardship.models import StewardAssignment

from .forms import LifePlanForm, PlanMemoryForm, WishesWorksheetForm
from .models import LifePlan, PlanMemory, WishesWorksheet


def get_or_create_plan(user) -> LifePlan:
    plan, _ = LifePlan.objects.get_or_create(
        owner=user,
        defaults={"memorial_preferred_name": user.full_display_name},
    )
    return plan


@login_required
def dashboard_view(request):
    """Main 'My Plan' private workspace screen."""
    plan = get_or_create_plan(request.user)
    memories = plan.memories.all()
    stewards = StewardAssignment.objects.filter(owner=request.user).exclude(
        status=StewardAssignment.Status.REVOKED
    )
    active_grants = AccessGrant.objects.filter(owner=request.user, revoked_at__isnull=True)
    incoming_grants = [
        g
        for g in AccessGrant.objects.filter(
            recipient_email__iexact=request.user.email, revoked_at__isnull=True
        ).select_related("owner")
        if g.is_currently_accessible_by(request.user)
    ]
    steward_for = StewardAssignment.objects.filter(
        steward_user=request.user,
        status=StewardAssignment.Status.ACCEPTED,
    ).select_related("owner")

    worksheet = WishesWorksheet.objects.filter(owner=request.user).first()

    return render(
        request,
        "planning/dashboard.html",
        {
            "plan": plan,
            "memories": memories,
            "stewards": stewards,
            "active_grants": active_grants,
            "incoming_grants": incoming_grants,
            "steward_for": steward_for,
            "worksheet": worksheet,
        },
    )


@login_required
def edit_plan_view(request):
    plan = get_or_create_plan(request.user)
    form = LifePlanForm(request.POST or None, request.FILES or None, instance=plan)
    if request.method == "POST" and form.is_valid():
        plan = form.save()
        record_audit(
            action="plan.updated",
            summary="Private plan preferences updated.",
            actor=request.user,
            subject_person_id=request.user.person_id,
            target_type="LifePlan",
            target_id=plan.id,
        )
        messages.success(
            request,
            "Your private plan has been saved. Remember: changing your plan never publishes anything automatically.",
        )
        return redirect("planning:dashboard")
    return render(request, "planning/edit_plan.html", {"form": form, "plan": plan})


@login_required
def add_memory_view(request):
    plan = get_or_create_plan(request.user)
    form = PlanMemoryForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        memory = form.save(commit=False)
        memory.plan = plan
        memory.save()
        if memory.photo_original:
            enqueue_photo_processing(str(memory.id))
        record_audit(
            action="plan.memory_added",
            summary=f"Memory added with audience '{memory.audience}'.",
            actor=request.user,
            subject_person_id=request.user.person_id,
            target_type="PlanMemory",
            target_id=memory.id,
        )
        messages.success(
            request,
            f"Memory saved. Audience: {memory.get_audience_display()}.",
        )
        return redirect("planning:dashboard")
    return render(request, "planning/memory_form.html", {"form": form, "plan": plan, "is_edit": False})


@login_required
def edit_memory_view(request, memory_id):
    plan = get_or_create_plan(request.user)
    memory = get_object_or_404(PlanMemory, id=memory_id, plan=plan)
    form = PlanMemoryForm(request.POST or None, request.FILES or None, instance=memory)
    if request.method == "POST" and form.is_valid():
        memory = form.save()
        if "photo_original" in request.FILES:
            enqueue_photo_processing(str(memory.id))
        record_audit(
            action="plan.memory_updated",
            summary=f"Memory updated with audience '{memory.audience}'.",
            actor=request.user,
            subject_person_id=request.user.person_id,
            target_type="PlanMemory",
            target_id=memory.id,
        )
        messages.success(request, "Memory updated.")
        return redirect("planning:dashboard")
    return render(
        request,
        "planning/memory_form.html",
        {"form": form, "plan": plan, "memory": memory, "is_edit": True},
    )


@login_required
@require_POST
def delete_memory_view(request, memory_id):
    plan = get_or_create_plan(request.user)
    memory = get_object_or_404(PlanMemory, id=memory_id, plan=plan)
    if memory.photo_original:
        memory.photo_original.delete(save=False)
    if memory.photo_display:
        memory.photo_display.delete(save=False)
    memory.delete()
    record_audit(
        action="plan.memory_deleted",
        summary="Private plan memory and its processed files were deleted.",
        actor=request.user,
        subject_person_id=request.user.person_id,
        target_type="PlanMemory",
        target_id=memory_id,
    )
    messages.success(request, "Memory and associated photo files permanently deleted.")
    return redirect("planning:dashboard")


@login_required
def plan_memory_media_view(request, memory_id):
    """Authenticated, permission-checked file handler for private plan memories.

    Only the owner OR an active accepted steward after verified death (for
    non-PRIVATE_ONLY memories) may fetch this image. Direct URLs never bypass checks.
    """
    memory = get_object_or_404(PlanMemory.objects.select_related("plan__owner"), id=memory_id)
    owner = memory.plan.owner

    allowed = False
    if request.user.id == owner.id:
        allowed = True
    elif owner.is_deceased_verified and memory.is_released_to_steward_after_death:
        allowed = StewardAssignment.objects.filter(
            owner=owner,
            steward_user=request.user,
            status=StewardAssignment.Status.ACCEPTED,
        ).exists()

    if not allowed:
        raise Http404("File not found.")

    field = memory.photo_display if memory.photo_display else memory.photo_original
    if not field or not field.name:
        raise Http404("No uploaded photograph for this memory.")

    resp = FileResponse(field.open("rb"), content_type="image/jpeg")
    resp["Cache-Control"] = "private, no-store"
    resp["X-Robots-Tag"] = "noindex, nofollow"
    return resp


@login_required
def shared_plan_view(request, owner_person_id):
    """View specific private planning instructions explicitly granted to the signed-in user."""
    from siteapp.accounts.models import User

    owner = get_object_or_404(User, person_id=owner_person_id)
    plan = get_object_or_404(LifePlan, owner=owner)

    grants = [
        g
        for g in AccessGrant.objects.filter(
            owner=owner,
            recipient_email__iexact=request.user.email,
            revoked_at__isnull=True,
        )
        if g.is_currently_accessible_by(request.user)
    ]
    if not grants:
        raise Http404("You do not have an active grant for this plan.")

    scopes = {g.scope for g in grants}
    from siteapp.events.models import FuneralContact

    contacts = (
        FuneralContact.objects.filter(owner=owner)
        if AccessGrant.Scope.CONTACT_LIST in scopes
        else []
    )

    resp = render(
        request,
        "planning/shared_plan.html",
        {
            "owner": owner,
            "plan": plan,
            "scopes": scopes,
            "grants": grants,
            "contacts": contacts,
        },
    )
    resp.vc_restricted = True
    return resp


@login_required
def wishes_wizard_view(request):
    """'Draft my wishes' private preparation wizard (NOT a legal will)."""
    worksheet, _ = WishesWorksheet.objects.get_or_create(
        owner=request.user,
        defaults={"jurisdiction": request.user.jurisdiction},
    )
    form = WishesWorksheetForm(request.POST or None, instance=worksheet)
    if request.method == "POST" and form.is_valid():
        ws = form.save()
        record_audit(
            action="planning.worksheet_saved",
            summary="Draft my wishes planning worksheet saved.",
            actor=request.user,
            subject_person_id=request.user.person_id,
            target_type="WishesWorksheet",
            target_id=ws.id,
        )
        messages.success(request, "Your private planning worksheet has been saved.")
        return redirect("planning:wishes_wizard")
    return render(
        request,
        "planning/wishes_wizard.html",
        {"form": form, "worksheet": worksheet},
    )


@login_required
def download_worksheet_view(request):
    """Download a readable, dated HTML worksheet to bring to an estate attorney."""
    worksheet, _ = WishesWorksheet.objects.get_or_create(
        owner=request.user,
        defaults={"jurisdiction": request.user.jurisdiction},
    )
    html = render_to_string(
        "planning/worksheet_export.html",
        {
            "worksheet": worksheet,
            "owner": request.user,
            "generated_at": timezone.now(),
        },
    )
    resp = HttpResponse(html, content_type="text/html; charset=utf-8")
    resp["Content-Disposition"] = 'attachment; filename="virtual-cemetery-wishes-worksheet.html"'
    resp["Cache-Control"] = "private, no-store"
    return resp


@login_required
def export_plan_archive_view(request):
    """Portability: export a readable HTML summary, structured JSON, and owned memory photos in a ZIP."""
    plan = get_or_create_plan(request.user)
    memories = list(plan.memories.all())
    worksheet = WishesWorksheet.objects.filter(owner=request.user).first()

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        readable_html = render_to_string(
            "planning/plan_export.html",
            {
                "owner": request.user,
                "plan": plan,
                "memories": memories,
                "worksheet": worksheet,
                "generated_at": timezone.now(),
            },
        )
        zf.writestr("my-plan-readable.html", readable_html)

        payload = {
            "exported_at": timezone.now().isoformat(),
            "person_id": str(request.user.person_id),
            "display_name": request.user.full_display_name,
            "jurisdiction": request.user.jurisdiction,
            "plan": {
                "memorial_preferred_name": plan.memorial_preferred_name,
                "birth_year": plan.birth_year,
                "biography_draft": plan.biography_draft,
                "disposition_preference": plan.disposition_preference,
                "disposition_notes": plan.disposition_notes,
                "service_wishes": plan.service_wishes,
                "emergency_contacts": plan.emergency_contacts,
                "important_document_locations": plan.important_document_locations,
                "memorial_audience_ceiling": plan.memorial_audience_ceiling,
                "allow_site_search": plan.allow_site_search,
                "updated_at": plan.updated_at.isoformat(),
            },
            "memories": [
                {
                    "id": str(m.id),
                    "title": m.title,
                    "year_taken": m.year_taken,
                    "story": m.story,
                    "alt_text": m.alt_text,
                    "audience": m.audience,
                    "source_label": m.source_label,
                }
                for m in memories
            ],
        }
        zf.writestr("my-plan-data.json", json.dumps(payload, indent=2))

        for m in memories:
            field = m.photo_display or m.photo_original
            if field and field.name:
                try:
                    with field.open("rb") as f:
                        zf.writestr(f"photos/{m.id}.jpg", f.read())
                except OSError:
                    pass

    record_audit(
        action="plan.exported",
        summary="Owner downloaded readable plan and memory archive.",
        actor=request.user,
        subject_person_id=request.user.person_id,
    )
    resp = HttpResponse(buf.getvalue(), content_type="application/zip")
    resp["Content-Disposition"] = 'attachment; filename="virtual-cemetery-my-plan-archive.zip"'
    resp["Cache-Control"] = "private, no-store"
    return resp
