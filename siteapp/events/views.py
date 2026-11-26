"""Views for private funeral contact lists, event setup, preview-before-send, idempotent delivery, and opt-out."""
from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from siteapp.accounts.models import AccessGrant, User, record_audit
from siteapp.jobs.tasks import enqueue_invitation_delivery
from siteapp.stewardship.services import is_active_organizer_for

from .forms import FuneralContactForm, FuneralEventForm
from .models import FuneralContact, FuneralEvent, InvitationDelivery


def _can_manage_owner_events(user: User, owner: User) -> bool:
    if user.id == owner.id:
        return True
    if not owner.is_deceased_verified:
        # While owner is living, only explicitly granted WHILE_ALIVE contact list access applies
        return False
    if is_active_organizer_for(user, owner):
        return True
    return any(
        g.is_currently_accessible_by(user)
        for g in AccessGrant.objects.filter(
            owner=owner,
            recipient_email__iexact=user.email,
            scope__in=[AccessGrant.Scope.FUNERAL_INSTRUCTIONS, AccessGrant.Scope.CONTACT_LIST],
            revoked_at__isnull=True,
        )
    )


@login_required
def contacts_view(request, owner_person_id=None):
    """Manage a private funeral contact list (owner or authorized organizer after verified death)."""
    owner = (
        get_object_or_404(User, person_id=owner_person_id)
        if owner_person_id
        else request.user
    )
    if not _can_manage_owner_events(request.user, owner):
        raise Http404("Not authorized to view this private contact list.")

    form = FuneralContactForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        email = form.cleaned_data["email"]
        contact, created = FuneralContact.objects.get_or_create(
            owner=owner,
            email=email,
            defaults={
                "full_name": form.cleaned_data["full_name"],
                "relationship": form.cleaned_data["relationship"],
                "source": "Manual entry",
            },
        )
        if created:
            messages.success(request, f"Added {contact.full_name} to the private funeral contact list.")
        else:
            messages.warning(
                request,
                f"{email} is already on this private list — duplicate prevented.",
            )
        return (
            redirect("events:owner_contacts", owner_person_id=owner.person_id)
            if owner_person_id
            else redirect("events:contacts")
        )

    contacts = FuneralContact.objects.filter(owner=owner)
    events = FuneralEvent.objects.filter(owner=owner)
    resp = render(
        request,
        "events/contacts.html",
        {"owner": owner, "form": form, "contacts": contacts, "events": events},
    )
    resp.vc_restricted = True
    return resp


@login_required
@require_POST
def delete_contact_view(request, contact_id):
    contact = get_object_or_404(FuneralContact, id=contact_id)
    if not _can_manage_owner_events(request.user, contact.owner):
        raise Http404("Not authorized.")
    owner_pid = contact.owner.person_id
    contact.delete()
    messages.info(request, "Contact removed from private list.")
    if owner_pid == request.user.person_id:
        return redirect("events:contacts")
    return redirect("events:owner_contacts", owner_person_id=owner_pid)


@login_required
def create_or_edit_event_view(request, owner_person_id, event_id=None):
    owner = get_object_or_404(User, person_id=owner_person_id)
    if not _can_manage_owner_events(request.user, owner):
        raise Http404("Not authorized to manage funeral events for this person.")

    event = (
        get_object_or_404(FuneralEvent, id=event_id, owner=owner)
        if event_id
        else None
    )
    form = FuneralEventForm(request.POST or None, instance=event)
    if request.method == "POST" and form.is_valid():
        ev = form.save(commit=False)
        ev.owner = owner
        ev.organizer = request.user
        if event and event.status == FuneralEvent.Status.CONFIRMED:
            ev.version = event.version + 1
        ev.save()
        record_audit(
            action="event.saved",
            summary=f"Funeral event saved (v{ev.version}). No invitations sent until organizer confirms preview.",
            actor=request.user,
            subject_person_id=owner.person_id,
            target_type="FuneralEvent",
            target_id=ev.id,
        )
        messages.success(request, "Event details saved. Please preview carefully before sending invitations.")
        return redirect("events:preview_event", event_id=ev.id)

    resp = render(
        request,
        "events/event_form.html",
        {"owner": owner, "event": event, "form": form},
    )
    resp.vc_restricted = True
    return resp


@login_required
def preview_event_view(request, event_id):
    """Organizer previews exact date, time zone, location, wording, and recipient list before sending."""
    event = get_object_or_404(FuneralEvent.objects.select_related("owner"), id=event_id)
    if not _can_manage_owner_events(request.user, event.owner):
        raise Http404("Not authorized.")

    contacts = FuneralContact.objects.filter(owner=event.owner)
    deliveries = event.deliveries.select_related("contact").all()
    can_send_now = bool(event.owner.is_deceased_verified) and event.status != FuneralEvent.Status.CANCELLED

    resp = render(
        request,
        "events/preview_send.html",
        {
            "event": event,
            "contacts": contacts,
            "deliveries": deliveries,
            "can_send_now": can_send_now,
        },
    )
    resp.vc_restricted = True
    return resp


@login_required
@require_POST
def send_invitations_view(request, event_id):
    """Idempotent one-time invitation queuing & delivery for the confirmed event version.

    Enforces:
    - Owner death must be verified (a pending/unverified report NEVER sends funeral mail!).
    - Duplicate sends for the same (event, version, contact) are strictly suppressed.
    - Recipients who opted out are skipped.
    """
    event = get_object_or_404(FuneralEvent.objects.select_related("owner"), id=event_id)
    if not _can_manage_owner_events(request.user, event.owner):
        raise Http404("Not authorized.")
    if not event.owner.is_deceased_verified:
        messages.error(
            request,
            "Funeral invitations cannot be sent until a death report has been verified and approved.",
        )
        return redirect("events:preview_event", event_id=event.id)
    if event.status == FuneralEvent.Status.CANCELLED:
        messages.error(request, "This event was cancelled.")
        return redirect("events:preview_event", event_id=event.id)

    selected_ids = request.POST.getlist("selected_contacts")
    contacts_qs = FuneralContact.objects.filter(owner=event.owner)
    if selected_ids:
        contacts_qs = contacts_qs.filter(id__in=selected_ids)

    queued_new = 0
    suppressed_duplicates = 0
    skipped_opt_outs = 0

    with transaction.atomic():
        event.status = FuneralEvent.Status.CONFIRMED
        event.save(update_fields=["status", "updated_at"])

        for contact in contacts_qs:
            idem_key = InvitationDelivery.build_idempotency_key(event, contact)
            existing = InvitationDelivery.objects.filter(idempotency_key=idem_key).first()
            if existing:
                # Duplicate send suppressed! Never double-send for same invitation version.
                suppressed_duplicates += 1
                continue

            if contact.opted_out:
                InvitationDelivery.objects.create(
                    event=event,
                    event_version=event.version,
                    contact=contact,
                    recipient_email=contact.email,
                    recipient_name=contact.full_name,
                    idempotency_key=idem_key,
                    status=InvitationDelivery.Status.OPTED_OUT,
                )
                skipped_opt_outs += 1
                continue

            delivery = InvitationDelivery.objects.create(
                event=event,
                event_version=event.version,
                contact=contact,
                recipient_email=contact.email,
                recipient_name=contact.full_name,
                idempotency_key=idem_key,
                status=InvitationDelivery.Status.QUEUED,
            )
            enqueue_invitation_delivery(str(delivery.id))
            queued_new += 1

    record_audit(
        action="event.invitations_queued",
        summary=f"Queued {queued_new} individual invitation(s), suppressed {suppressed_duplicates} duplicate(s), skipped {skipped_opt_outs} opt-out(s).",
        actor=request.user,
        subject_person_id=event.owner.person_id,
        target_type="FuneralEvent",
        target_id=event.id,
    )
    messages.success(
        request,
        f"Processed invitations: {queued_new} queued for individual delivery, "
        f"{suppressed_duplicates} duplicate(s) suppressed, {skipped_opt_outs} opted-out skipped.",
    )
    return redirect("events:preview_event", event_id=event.id)


def recipient_opt_out_view(request, token):
    """One-click opt-out link in funeral invitations so recipients can decline further messages."""
    contact = get_object_or_404(FuneralContact, opt_out_token=token)
    if request.method == "POST":
        contact.opted_out = True
        contact.save(update_fields=["opted_out"])
        messages.success(
            request,
            "You have opted out. You will not receive further funeral or memorial notices from this list.",
        )
    return render(request, "events/opt_out.html", {"contact": contact})
