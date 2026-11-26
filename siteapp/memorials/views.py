"""Views for homepage, owner preview, memorial publishing, guestbook, relationships, search, and printable view."""
from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import FileResponse, Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from siteapp.accounts.models import User, record_audit
from siteapp.integrations.email_provider import send_transactional_email
from siteapp.planning.models import LifePlan, PlanMemory
from siteapp.planning.views import get_or_create_plan
from siteapp.stewardship.services import is_active_steward_for
from siteapp.storage import get_media_storage

from .forms import (
    AbuseReportForm,
    FamilyCreatedMemorialForm,
    GuestbookEntryForm,
    MemorialInviteForm,
    RelationshipProposalForm,
)
from .models import (
    GuestbookEntry,
    Memorial,
    MemorialInvite,
    MemorialRelationship,
    PublishedMemory,
)
from .services import (
    can_manage_memorial,
    can_view_memorial,
    publish_memorial_snapshot,
    visible_relationships_for,
)


def health_check_view(request):
    return JsonResponse({"status": "ok", "service": "virtual-cemetery"})


def home_view(request):
    """Dignified landing page explaining My Plan vs. The Memorial and featuring opt-in public memorials."""
    featured_public = Memorial.objects.filter(
        status=Memorial.Status.PUBLISHED,
        audience=Memorial.Audience.PUBLIC,
        allow_site_search=True,
    )[:3]
    return render(request, "home.html", {"featured_memorials": featured_public})


def policies_view(request):
    """Pilot review, evidence retention, appeal, deletion, succession, and closure commitments."""
    return render(request, "policies.html")


def discover_view(request):
    """Optional public search — ONLY includes published, explicitly public, search-opted-in memorials."""
    q = (request.GET.get("q") or "").strip()
    qs = Memorial.objects.filter(
        status=Memorial.Status.PUBLISHED,
        audience=Memorial.Audience.PUBLIC,
        allow_site_search=True,
    )
    if q:
        qs = qs.filter(Q(full_name__icontains=q) | Q(biography__icontains=q))
    paginator = Paginator(qs, 12)
    page_obj = paginator.get_page(request.GET.get("page"))
    return render(request, "memorials/discover.html", {"page_obj": page_obj, "query": q})


@login_required
def owner_preview_view(request):
    """Allows a living owner to preview exactly how their memorial will look to an invited visitor."""
    plan = get_or_create_plan(request.user)
    eligible_memories = plan.memories.filter(
        audience__in=[PlanMemory.Audience.INVITED_MEMORIAL, PlanMemory.Audience.PUBLIC_MEMORIAL]
    )
    private_count = plan.memories.exclude(
        audience__in=[PlanMemory.Audience.INVITED_MEMORIAL, PlanMemory.Audience.PUBLIC_MEMORIAL]
    ).count()
    resp = render(
        request,
        "memorials/owner_preview.html",
        {
            "plan": plan,
            "eligible_memories": eligible_memories,
            "private_count": private_count,
        },
    )
    resp.vc_restricted = True
    return resp


@login_required
def prepare_release_view(request, owner_person_id):
    """Steward screen after verified death to select eligible memories, preview, and publish."""
    owner = get_object_or_404(User, person_id=owner_person_id)
    if not owner.is_deceased_verified or not is_active_steward_for(request.user, owner):
        raise Http404("Release preparation is available only to an active steward after verified death.")

    plan = get_object_or_404(LifePlan, owner=owner)
    eligible_memories = plan.memories.filter(
        audience__in=[PlanMemory.Audience.INVITED_MEMORIAL, PlanMemory.Audience.PUBLIC_MEMORIAL]
    )
    existing_memorial = Memorial.objects.filter(owner=owner).first()

    if request.method == "POST":
        selected_ids = request.POST.getlist("selected_memories")
        chosen_audience = request.POST.get("audience", Memorial.Audience.INVITED_ONLY)
        allow_search = request.POST.get("allow_site_search") == "on"
        steward_tribute = request.POST.get("steward_tribute", "")

        memorial = publish_memorial_snapshot(
            owner=owner,
            steward=request.user,
            selected_memory_ids=selected_ids,
            chosen_audience=chosen_audience,
            allow_site_search=allow_search,
            steward_tribute=steward_tribute,
        )
        messages.success(
            request,
            "Memorial published from the approved snapshot. Funeral invitations remain a separate action.",
        )
        return redirect("memorials:detail", slug=memorial.slug)

    resp = render(
        request,
        "memorials/prepare_release.html",
        {
            "owner": owner,
            "plan": plan,
            "eligible_memories": eligible_memories,
            "existing_memorial": existing_memorial,
        },
    )
    resp.vc_restricted = True
    return resp


def memorial_detail_view(request, slug):
    """The Memorial page — reads strictly from the Published Memorial snapshot, never LifePlan."""
    memorial = get_object_or_404(Memorial, slug=slug)
    if not can_view_memorial(request.user, memorial):
        raise Http404("This memorial is private or unavailable.")

    is_manager = can_manage_memorial(request.user, memorial)
    memories = memorial.published_memories.all()
    relationships = visible_relationships_for(memorial, request.user)

    # Guestbook pagination & strict pending-note visibility (pending visible ONLY to author and manager)
    entries_qs = memorial.guestbook_entries.select_related("author")
    if is_manager:
        visible_entries = entries_qs.exclude(status=GuestbookEntry.ModerationStatus.HIDDEN)
        hidden_entries = entries_qs.filter(status=GuestbookEntry.ModerationStatus.HIDDEN)
    elif request.user.is_authenticated:
        visible_entries = entries_qs.filter(
            Q(status=GuestbookEntry.ModerationStatus.APPROVED)
            | Q(status=GuestbookEntry.ModerationStatus.PENDING, author=request.user)
        )
        hidden_entries = GuestbookEntry.objects.none()
    else:
        visible_entries = entries_qs.filter(status=GuestbookEntry.ModerationStatus.APPROVED)
        hidden_entries = GuestbookEntry.objects.none()

    paginator = Paginator(visible_entries, 10)
    guestbook_page = paginator.get_page(request.GET.get("page"))

    flower_count = memorial.guestbook_entries.filter(
        status=GuestbookEntry.ModerationStatus.APPROVED
    ).exclude(flower="").count()

    guestbook_form = GuestbookEntryForm()
    invite_form = MemorialInviteForm() if is_manager else None
    rel_form = RelationshipProposalForm() if is_manager else None
    pending_rel_requests = (
        MemorialRelationship.objects.filter(
            to_memorial=memorial, status=MemorialRelationship.Status.PROPOSED
        ).select_related("from_memorial")
        if is_manager
        else []
    )
    active_invites = (
        memorial.invites.filter(revoked_at__isnull=True) if is_manager else []
    )

    resp = render(
        request,
        "memorials/detail.html",
        {
            "memorial": memorial,
            "is_manager": is_manager,
            "memories": memories,
            "relationships": relationships,
            "guestbook_page": guestbook_page,
            "hidden_entries": hidden_entries,
            "flower_count": flower_count,
            "guestbook_form": guestbook_form,
            "invite_form": invite_form,
            "rel_form": rel_form,
            "pending_rel_requests": pending_rel_requests,
            "active_invites": active_invites,
        },
    )
    if memorial.audience != Memorial.Audience.PUBLIC or memorial.status != Memorial.Status.PUBLISHED:
        resp.vc_restricted = True
    return resp


def memorial_print_view(request, slug):
    """Accessible, printer-friendly memorial sheet."""
    memorial = get_object_or_404(Memorial, slug=slug)
    if not can_view_memorial(request.user, memorial):
        raise Http404("This memorial is private or unavailable.")
    memories = memorial.published_memories.all()
    entries = memorial.guestbook_entries.filter(status=GuestbookEntry.ModerationStatus.APPROVED)[:50]
    resp = render(
        request,
        "memorials/print.html",
        {"memorial": memorial, "memories": memories, "entries": entries},
    )
    if memorial.audience != Memorial.Audience.PUBLIC:
        resp.vc_restricted = True
    return resp


def published_memory_image_view(request, slug, memory_id):
    """Permission-checked image handler for published memorial photographs."""
    memorial = get_object_or_404(Memorial, slug=slug)
    if not can_view_memorial(request.user, memorial):
        raise Http404("File not found.")
    pm = get_object_or_404(PublishedMemory, id=memory_id, memorial=memorial)
    if not pm.display_media_path:
        raise Http404("No uploaded display file.")
    storage = get_media_storage()
    if not storage.exists(pm.display_media_path):
        raise Http404("Display file unavailable.")
    resp = FileResponse(storage.open(pm.display_media_path, "rb"), content_type="image/jpeg")
    if memorial.audience != Memorial.Audience.PUBLIC:
        resp["Cache-Control"] = "private, no-store"
        resp["X-Robots-Tag"] = "noindex, nofollow"
    return resp


def published_portrait_image_view(request, slug):
    memorial = get_object_or_404(Memorial, slug=slug)
    if not can_view_memorial(request.user, memorial):
        raise Http404("File not found.")
    if not memorial.portrait_storage_path:
        raise Http404("No portrait uploaded.")
    storage = get_media_storage()
    if not storage.exists(memorial.portrait_storage_path):
        raise Http404("Portrait unavailable.")
    resp = FileResponse(storage.open(memorial.portrait_storage_path, "rb"), content_type="image/jpeg")
    if memorial.audience != Memorial.Audience.PUBLIC:
        resp["Cache-Control"] = "private, no-store"
    return resp


@login_required
@require_POST
def add_guestbook_entry_view(request, slug):
    memorial = get_object_or_404(Memorial, slug=slug)
    if not can_view_memorial(request.user, memorial) or not memorial.guestbook_open:
        raise Http404("Guestbook is unavailable.")

    form = GuestbookEntryForm(request.POST)
    if form.is_valid():
        entry = form.save(commit=False)
        entry.memorial = memorial
        entry.author = request.user
        entry.author_display_name = request.user.full_display_name
        # Default to approval required for notes; flowers without notes or when approval disabled appear immediately
        if memorial.guestbook_requires_approval and entry.message.strip() and not can_manage_memorial(
            request.user, memorial
        ):
            entry.status = GuestbookEntry.ModerationStatus.PENDING
            msg = "Thank you. Your note has been sent to the steward for approval before other visitors see it."
        else:
            entry.status = GuestbookEntry.ModerationStatus.APPROVED
            msg = "Your tribute has been added to the memorial."
        entry.save()
        messages.success(request, msg)
    else:
        messages.error(request, "Please select a flower or enter a note.")
    return redirect("memorials:detail", slug=memorial.slug)


@login_required
@require_POST
def moderate_guestbook_view(request, slug, entry_id):
    memorial = get_object_or_404(Memorial, slug=slug)
    entry = get_object_or_404(GuestbookEntry, id=entry_id, memorial=memorial)
    action = request.POST.get("action")

    # Visitors can always remove their own contribution
    if action == "delete_own" and entry.author_id == request.user.id:
        entry.delete()
        messages.info(request, "Your contribution has been removed.")
        return redirect("memorials:detail", slug=memorial.slug)

    if not can_manage_memorial(request.user, memorial):
        raise Http404("Not authorized.")

    if action == "approve":
        entry.status = GuestbookEntry.ModerationStatus.APPROVED
        entry.save(update_fields=["status"])
        messages.success(request, "Guestbook note approved.")
    elif action == "hide":
        entry.status = GuestbookEntry.ModerationStatus.HIDDEN
        entry.save(update_fields=["status"])
        messages.info(request, "Guestbook note hidden.")
    return redirect("memorials:detail", slug=memorial.slug)


@login_required
@require_POST
def toggle_guestbook_view(request, slug):
    memorial = get_object_or_404(Memorial, slug=slug)
    if not can_manage_memorial(request.user, memorial):
        raise Http404("Not authorized.")
    memorial.guestbook_open = not memorial.guestbook_open
    memorial.save(update_fields=["guestbook_open", "updated_at"])
    messages.info(
        request,
        "Guestbook is now open." if memorial.guestbook_open else "Guestbook has been closed to new notes.",
    )
    return redirect("memorials:detail", slug=memorial.slug)


@login_required
@require_POST
def change_memorial_audience_view(request, slug):
    """Manager narrows or adjusts audience within owner's ceiling (e.g., making a public page private)."""
    memorial = get_object_or_404(Memorial, slug=slug)
    if not can_manage_memorial(request.user, memorial):
        raise Http404("Not authorized.")
    new_audience = request.POST.get("audience")
    if new_audience == Memorial.Audience.INVITED_ONLY:
        memorial.audience = Memorial.Audience.INVITED_ONLY
        memorial.allow_site_search = False
        memorial.save(update_fields=["audience", "allow_site_search", "updated_at"])
        record_audit(
            action="memorial.audience_narrowed",
            summary="Memorial changed to invited-only and removed from site search.",
            actor=request.user,
            subject_person_id=memorial.person_id,
            target_type="Memorial",
            target_id=memorial.id,
        )
        messages.success(request, "Memorial is now invited-only and removed from public search.")
    elif new_audience == Memorial.Audience.PUBLIC:
        # Respect owner ceiling
        plan = LifePlan.objects.filter(owner=memorial.owner).first() if memorial.owner_id else None
        if plan and plan.memorial_audience_ceiling != LifePlan.MemorialAudienceCeiling.PUBLIC:
            messages.error(request, "The account owner set this memorial's ceiling to Invited-only.")
        else:
            memorial.audience = Memorial.Audience.PUBLIC
            memorial.save(update_fields=["audience", "updated_at"])
            messages.success(request, "Memorial audience updated to Public.")
    return redirect("memorials:detail", slug=memorial.slug)


@login_required
@require_POST
def create_memorial_invite_view(request, slug):
    memorial = get_object_or_404(Memorial, slug=slug)
    if not can_manage_memorial(request.user, memorial):
        raise Http404("Not authorized.")
    form = MemorialInviteForm(request.POST)
    if form.is_valid():
        inv = form.save(commit=False)
        inv.memorial = memorial
        inv.invited_by = request.user
        inv.save()
        redeem_url = request.build_absolute_uri(
            reverse("memorials:redeem_invite", kwargs={"token": inv.token})
        )
        send_transactional_email(
            to_email=inv.intended_email,
            to_name=inv.intended_name or inv.intended_email,
            subject=f"You are invited to visit the memorial for {memorial.full_name}",
            body=(
                f"Hello {inv.intended_name or 'friend'},\n\n"
                f"You have been invited to visit the private Virtual Cemetery memorial for {memorial.full_name}.\n"
                f"Sign in with {inv.intended_email} and open this link before {inv.expires_at:%B %d, %Y}:\n{redeem_url}\n"
            ),
            idempotency_key=f"memorial-invite-{inv.id}",
        )
        messages.success(request, f"Private memorial invitation created for {inv.intended_email}.")
    return redirect("memorials:detail", slug=memorial.slug)


@login_required
def redeem_memorial_invite_view(request, token):
    """Intended recipient redeems an expiring private-page invitation."""
    invite = get_object_or_404(MemorialInvite.objects.select_related("memorial"), token=token)
    if invite.revoked_at is not None or timezone.now() > invite.expires_at:
        return render(request, "memorials/invite_expired.html", {"invite": invite}, status=410)

    if invite.intended_email.lower() != request.user.email.lower():
        messages.error(
            request,
            f"This private memorial invitation was issued specifically for {invite.intended_email}.",
        )
        return redirect("home")

    if invite.redeemed_by_id is None:
        invite.redeemed_by = request.user
        invite.redeemed_at = timezone.now()
        invite.save(update_fields=["redeemed_by", "redeemed_at"])

    messages.success(request, f"Welcome to the memorial for {invite.memorial.full_name}.")
    return redirect("memorials:detail", slug=invite.memorial.slug)


@login_required
@require_POST
def propose_relationship_view(request, slug):
    memorial = get_object_or_404(Memorial, slug=slug)
    if not can_manage_memorial(request.user, memorial):
        raise Http404("Not authorized.")
    form = RelationshipProposalForm(request.POST)
    if form.is_valid():
        target = Memorial.objects.filter(slug=form.cleaned_data["target_slug"]).first()
        if not target or target.id == memorial.id:
            messages.error(request, "Could not find another memorial with that address slug.")
        else:
            MemorialRelationship.objects.create(
                from_memorial=memorial,
                to_memorial=target,
                label_from_to=form.cleaned_data["label_from_to"],
                label_to_from=form.cleaned_data["label_to_from"],
                proposed_by=request.user,
                from_approved=True,
                to_approved=False,
                status=MemorialRelationship.Status.PROPOSED,
            )
            messages.success(
                request,
                f"Relationship proposed with {target.full_name}. It will appear only after their steward or owner agrees.",
            )
    return redirect("memorials:detail", slug=memorial.slug)


@login_required
@require_POST
def respond_relationship_view(request, slug, relationship_id):
    memorial = get_object_or_404(Memorial, slug=slug)
    if not can_manage_memorial(request.user, memorial):
        raise Http404("Not authorized.")
    rel = get_object_or_404(
        MemorialRelationship,
        Q(id=relationship_id) & (Q(from_memorial=memorial) | Q(to_memorial=memorial)),
    )
    action = request.POST.get("action")
    if action == "accept" and rel.to_memorial_id == memorial.id:
        rel.accept_target_side()
        messages.success(request, "Relationship accepted. It is shown only to visitors allowed to see both memorials.")
    elif action == "withdraw":
        rel.withdraw()
        messages.info(request, "Relationship link withdrawn immediately.")
    return redirect("memorials:detail", slug=memorial.slug)


@login_required
def report_abuse_view(request, slug):
    memorial = get_object_or_404(Memorial, slug=slug)
    if not can_view_memorial(request.user, memorial):
        raise Http404("Not found.")
    entry_id = request.GET.get("entry") or request.POST.get("entry_id")
    entry = GuestbookEntry.objects.filter(id=entry_id, memorial=memorial).first() if entry_id else None
    form = AbuseReportForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        rep = form.save(commit=False)
        rep.memorial = memorial
        rep.guestbook_entry = entry
        rep.reported_by = request.user
        rep.save()
        record_audit(
            action="memorial.abuse_reported",
            summary="Visitor reported abuse or requested takedown.",
            actor=request.user,
            subject_person_id=memorial.person_id,
            target_type="AbuseReport",
            target_id=rep.id,
        )
        messages.success(request, "Your report has been recorded for the memorial steward and site support.")
        return redirect("memorials:detail", slug=memorial.slug)
    return render(
        request,
        "memorials/report_abuse.html",
        {"memorial": memorial, "entry": entry, "form": form},
    )


@login_required
def family_create_memorial_view(request):
    """Separate flow for a loved one who passed away without a Virtual Cemetery account."""
    form = FamilyCreatedMemorialForm(request.POST or None)
    possible_duplicates = []
    if request.method == "POST" and form.is_valid():
        name = form.cleaned_data["full_name"]
        possible_duplicates = list(Memorial.objects.filter(full_name__iexact=name))
        if possible_duplicates and request.POST.get("confirm_not_duplicate") != "yes":
            messages.warning(
                request,
                "We found an existing memorial with a matching name. Please confirm this is not a duplicate before creating.",
            )
        else:
            mem = form.save(commit=False)
            mem.is_family_created = True
            mem.created_by_label = f"Family-created by {request.user.full_display_name}"
            mem.published_by = request.user
            mem.published_at = timezone.now()
            mem.status = Memorial.Status.PUBLISHED
            mem.allow_site_search = False
            mem.save()
            record_audit(
                action="memorial.family_created",
                summary="Family-created memorial published for loved one without prior account.",
                actor=request.user,
                subject_person_id=mem.person_id,
                target_type="Memorial",
                target_id=mem.id,
            )
            messages.success(
                request,
                "Family-created memorial published and clearly labeled with your name.",
            )
            return redirect("memorials:detail", slug=mem.slug)
    return render(
        request,
        "memorials/family_create.html",
        {"form": form, "possible_duplicates": possible_duplicates},
    )
