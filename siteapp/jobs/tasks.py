"""Background job runners and Google Cloud Tasks dispatcher.

- Photo processing: validates file, strips EXIF/GPS location metadata via Pillow,
  creates safe resized JPEG display copy.
- Invitation delivery: rechecks event cancellation, verified death status, and
  recipient opt-out before sending. Handles ambiguous provider timeouts by
  marking NEEDS_RECONCILIATION instead of blind retrying.
- Evidence purge: deletes expired case evidence files from the isolated evidence
  storage on schedule.
"""
from __future__ import annotations

import io
import json
import logging
from django.conf import settings
from django.core.files.base import ContentFile
from django.urls import reverse
from django.utils import timezone
from PIL import Image, ImageOps

from siteapp.accounts.models import record_audit
from siteapp.integrations.email_provider import AmbiguousDeliveryTimeout, send_transactional_email

logger = logging.getLogger(__name__)


def _enqueue_cloud_task(path: str, payload: dict) -> bool:
    """Dispatch an authenticated HTTP task to the private Cloud Run worker via Cloud Tasks."""
    if not settings.CLOUD_TASKS_ENABLED:
        return False

    from google.cloud import tasks_v2  # Lazy import

    client = tasks_v2.CloudTasksClient()
    parent = client.queue_path(
        settings.GCP_PROJECT_ID,
        settings.GCP_TASKS_LOCATION,
        settings.GCP_TASKS_QUEUE_NAME,
    )
    url = f"{settings.WORKER_BASE_URL.rstrip('/')}{path}"
    task = {
        "http_request": {
            "http_method": tasks_v2.HttpMethod.POST,
            "url": url,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps(payload).encode("utf-8"),
            "oidc_token": {
                "service_account_email": settings.WORKER_OIDC_SERVICE_ACCOUNT,
                "audience": settings.WORKER_BASE_URL.rstrip("/"),
            },
        }
    }
    client.create_task(request={"parent": parent, "task": task})
    return True


def enqueue_photo_processing(memory_id: str) -> None:
    if not _enqueue_cloud_task("/jobs/process-photo/", {"memory_id": memory_id}):
        process_plan_memory_photo(memory_id)


def enqueue_invitation_delivery(delivery_id: str) -> None:
    if not _enqueue_cloud_task("/jobs/send-invitation/", {"delivery_id": delivery_id}):
        deliver_funeral_invitation(delivery_id)


def process_plan_memory_photo(memory_id: str) -> bool:
    """Validate uploaded photo, strip EXIF/GPS metadata, and write safe display JPEG."""
    from siteapp.planning.models import PlanMemory

    memory = PlanMemory.objects.filter(id=memory_id).first()
    if not memory or not memory.photo_original or not memory.photo_original.name:
        return False

    try:
        with memory.photo_original.open("rb") as fh:
            with Image.open(fh) as img:
                img.verify()
        with memory.photo_original.open("rb") as fh:
            with Image.open(fh) as img:
                clean_img = ImageOps.exif_transpose(img).convert("RGB")
                clean_img.thumbnail((1600, 1600), Image.Resampling.LANCZOS)
                out = io.BytesIO()
                # Saving cleanly without exif=... strips all camera & GPS EXIF metadata
                clean_img.save(out, format="JPEG", quality=84, optimize=True)
                out.seek(0)
                memory.photo_display.save(
                    f"{memory.id}.jpg",
                    ContentFile(out.read()),
                    save=False,
                )
        memory.media_status = PlanMemory.MediaStatus.READY
        memory.save(update_fields=["photo_display", "media_status", "updated_at"])
        return True
    except Exception as exc:
        logger.warning("Photo processing rejected memory %s: %s", memory_id, type(exc).__name__)
        memory.media_status = PlanMemory.MediaStatus.REJECTED
        memory.save(update_fields=["media_status", "updated_at"])
        return False


def deliver_funeral_invitation(delivery_id: str, *, simulate_timeout: bool = False) -> str:
    """Execute a single idempotent funeral invitation delivery.

    Always rechecks cancellation, owner's verified death status, and recipient opt-out.
    Refuses to blindly retry deliveries in NEEDS_RECONCILIATION or SENT states.
    """
    from siteapp.events.models import FuneralEvent, InvitationDelivery

    delivery = (
        InvitationDelivery.objects.select_related("event", "event__owner", "contact")
        .filter(id=delivery_id)
        .first()
    )
    if not delivery:
        return "missing"

    # Idempotency guard: never re-send SENT, CANCELLED, OPTED_OUT, or ambiguous deliveries
    if delivery.status in (
        InvitationDelivery.Status.SENT,
        InvitationDelivery.Status.CANCELLED,
        InvitationDelivery.Status.OPTED_OUT,
        InvitationDelivery.Status.NEEDS_RECONCILIATION,
    ):
        return delivery.status

    event = delivery.event
    owner = event.owner
    contact = delivery.contact

    # Recheck live preconditions at worker execution time!
    if event.status == FuneralEvent.Status.CANCELLED or not owner.is_deceased_verified:
        delivery.status = InvitationDelivery.Status.CANCELLED
        delivery.last_error = "Stopped by worker recheck: event cancelled or death verification not active."
        delivery.save(update_fields=["status", "last_error", "updated_at"])
        return delivery.status

    if contact.opted_out:
        delivery.status = InvitationDelivery.Status.OPTED_OUT
        delivery.save(update_fields=["status", "updated_at"])
        return delivery.status

    opt_out_url = f"{settings.SITE_BASE_URL}{reverse('events:opt_out', kwargs={'token': contact.opt_out_token})}"
    event_time_str = (
        f"{event.event_datetime:%B %d, %Y at %I:%M %p} ({event.time_zone})"
        if event.event_datetime
        else f"Time to be confirmed ({event.time_zone})"
    )
    body_lines = [
        f"Dear {contact.full_name},",
        "",
        f"You are invited to attend: {event.title}",
        f"In remembrance of: {owner.full_display_name}",
        f"When: {event_time_str}",
    ]
    if event.location_name:
        body_lines.append(f"Where: {event.location_name}")
    if event.location_address:
        body_lines.append(event.location_address)
    if event.livestream_url:
        body_lines.append(f"Private livestream (for invited guests only): {event.livestream_url}")
    if event.invitation_wording:
        body_lines.extend(["", event.invitation_wording])
    body_lines.extend(
        [
            "",
            "---",
            "This notice was sent individually by the family's authorized funeral organizer.",
            f"To decline any further messages from this list, visit: {opt_out_url}",
        ]
    )

    delivery.attempt_count += 1
    try:
        if simulate_timeout:
            raise AmbiguousDeliveryTimeout("Simulated provider HTTP timeout after request transmission.")

        provider_msg_id = send_transactional_email(
            to_email=delivery.recipient_email,
            to_name=delivery.recipient_name,
            subject=f"Invitation: {event.title} — {owner.full_display_name}",
            body="\n".join(body_lines),
            idempotency_key=delivery.idempotency_key,
        )
        delivery.status = InvitationDelivery.Status.SENT
        delivery.provider_message_id = provider_msg_id
        delivery.sent_at = timezone.now()
        delivery.last_error = ""
        delivery.save(
            update_fields=["status", "provider_message_id", "sent_at", "last_error", "attempt_count", "updated_at"]
        )
        return delivery.status
    except AmbiguousDeliveryTimeout as exc:
        # Critical architecture rule: ambiguous delivery goes to reconciliation before any retry!
        delivery.status = InvitationDelivery.Status.NEEDS_RECONCILIATION
        delivery.last_error = str(exc)
        delivery.save(update_fields=["status", "last_error", "attempt_count", "updated_at"])
        record_audit(
            action="event.delivery_needs_reconciliation",
            summary="Invitation delivery timed out ambiguously; held for reconciliation before retry.",
            subject_person_id=owner.person_id,
            target_type="InvitationDelivery",
            target_id=delivery.id,
        )
        return delivery.status
    except Exception as exc:
        delivery.status = InvitationDelivery.Status.FAILED
        delivery.last_error = f"{type(exc).__name__}: {exc}"
        delivery.save(update_fields=["status", "last_error", "attempt_count", "updated_at"])
        return delivery.status


def purge_expired_case_evidence() -> int:
    """Delete case evidence files whose scheduled retention window has elapsed."""
    from siteapp.stewardship.models import DeathReport

    now = timezone.now()
    expired = DeathReport.objects.filter(
        evidence_purged_at__isnull=True,
        evidence_scheduled_purge_at__lte=now,
    ).exclude(evidence_file="")

    purged_count = 0
    for report in expired:
        if report.evidence_file and report.evidence_file.name:
            report.evidence_file.delete(save=False)
        report.evidence_purged_at = now
        report.save(update_fields=["evidence_file", "evidence_purged_at", "updated_at"])
        record_audit(
            action="staff.evidence_purged",
            summary="Scheduled evidence file retention purge completed.",
            subject_person_id=report.subject_owner.person_id,
            target_type="DeathReport",
            target_id=report.id,
        )
        purged_count += 1
    return purged_count
