"""Domain services for atomic verification approval, conflict pause, and full mistaken-death reversal."""
from __future__ import annotations

from django.db import transaction
from django.utils import timezone

from siteapp.accounts.models import User, record_audit
from siteapp.events.models import InvitationDelivery
from siteapp.memorials.models import Memorial, MemorialInvite

from .models import DeathReport, StewardAssignment, VerificationDecision


def is_active_steward_for(user: User | None, owner: User) -> bool:
    """Always recheck live database status — revoked stewards lose access immediately."""
    if not user or not user.is_authenticated:
        return False
    return StewardAssignment.objects.filter(
        owner=owner,
        steward_user=user,
        status=StewardAssignment.Status.ACCEPTED,
        revoked_at__isnull=True,
    ).exists()


def is_active_organizer_for(user: User | None, owner: User) -> bool:
    if not user or not user.is_authenticated:
        return False
    if user.id == owner.id:
        return True
    return StewardAssignment.objects.filter(
        owner=owner,
        steward_user=user,
        status=StewardAssignment.Status.ACCEPTED,
        revoked_at__isnull=True,
        can_organize_funeral=True,
    ).exists()


@transaction.atomic
def approve_death_report(report: DeathReport, reviewer: User, reason: str) -> VerificationDecision:
    """Atomically approve a verified death report and record the reviewer's decision.

    Requires independent evidence checked and owner challenge outreach sent.
    Does NOT automatically publish the memorial or send funeral invitations —
    those remain separate, explicit steward/organizer actions.
    """
    if not report.independent_evidence_checked or not report.owner_challenge_sent_at:
        raise ValueError(
            "Both independent evidence verification and owner challenge outreach are required before approval."
        )
    if report.status == DeathReport.Status.CONFLICT_PAUSED and (
        not report.second_reviewer_id or report.second_reviewer_id == reviewer.id
    ):
        raise ValueError("A conflicting case requires sign-off by a second independent reviewer.")

    now = timezone.now()
    owner = report.subject_owner
    owner.is_deceased_verified = True
    owner.death_verified_at = now
    owner.save(update_fields=["is_deceased_verified", "death_verified_at"])

    report.status = DeathReport.Status.APPROVED
    report.save(update_fields=["status", "updated_at"])

    decision = VerificationDecision.objects.create(
        report=report,
        reviewer=reviewer,
        action=VerificationDecision.Action.APPROVED,
        reason=reason,
    )
    record_audit(
        action="verification.approved",
        summary="Death report verified and approved; released planning access enabled for accepted steward.",
        actor=reviewer,
        subject_person_id=owner.person_id,
        target_type="DeathReport",
        target_id=report.id,
    )
    return decision


@transaction.atomic
def reverse_death_report(report: DeathReport, reviewer: User, reason: str) -> dict:
    """Full mistaken-death reversal drill:
    1. Restore owner's living status and account access.
    2. Suspend/unpublish any published memorial for that owner.
    3. Revoke all active memorial invite links.
    4. Cancel all unsent/queued funeral invitation jobs.
    5. Capture an immutable record of recipients who already received a delivered notice
       so support can send an accurate correction.
    """
    now = timezone.now()
    owner = report.subject_owner

    # 1. Restore owner account
    owner.is_deceased_verified = False
    owner.death_verified_at = None
    owner.is_active = True
    owner.save(update_fields=["is_deceased_verified", "death_verified_at", "is_active"])

    # 2. Unpublish / suspend memorial & 3. Revoke invite links
    memorials_suspended = 0
    invites_revoked = 0
    for memorial in Memorial.objects.filter(owner=owner):
        if memorial.status == Memorial.Status.PUBLISHED:
            memorial.status = Memorial.Status.SUSPENDED
            memorial.allow_site_search = False
            memorial.save(update_fields=["status", "allow_site_search", "updated_at"])
            memorials_suspended += 1
        invites_revoked += MemorialInvite.objects.filter(
            memorial=memorial, revoked_at__isnull=True
        ).update(revoked_at=now)

    # 4. Stop queued / pending funeral invitation deliveries
    cancelled_jobs = InvitationDelivery.objects.filter(
        event__owner=owner,
        status__in=[
            InvitationDelivery.Status.QUEUED,
            InvitationDelivery.Status.PENDING,
            InvitationDelivery.Status.NEEDS_RECONCILIATION,
        ],
    ).update(
        status=InvitationDelivery.Status.CANCELLED,
        last_error="Cancelled due to death-verification reversal.",
        updated_at=now,
    )

    # 5. Snapshot already-delivered notices for follow-up correction
    delivered = list(
        InvitationDelivery.objects.filter(
            event__owner=owner,
            status=InvitationDelivery.Status.SENT,
        ).values("id", "recipient_email", "recipient_name", "sent_at", "event_id")
    )
    serializable_delivered = [
        {
            "delivery_id": str(d["id"]),
            "recipient_email": d["recipient_email"],
            "recipient_name": d["recipient_name"],
            "sent_at": d["sent_at"].isoformat() if d["sent_at"] else None,
            "event_id": str(d["event_id"]),
        }
        for d in delivered
    ]

    report.status = DeathReport.Status.REVERSED
    report.erroneous_notices_snapshot = serializable_delivered
    report.save(update_fields=["status", "erroneous_notices_snapshot", "updated_at"])

    VerificationDecision.objects.create(
        report=report,
        reviewer=reviewer,
        action=VerificationDecision.Action.REVERSED,
        reason=reason,
    )
    record_audit(
        action="verification.reversed",
        summary=(
            f"Death verification reversed; owner restored; {memorials_suspended} memorial(s) suspended, "
            f"{invites_revoked} invite(s) revoked, {cancelled_jobs} queued notice(s) cancelled, "
            f"{len(serializable_delivered)} delivered notice(s) recorded for correction."
        ),
        actor=reviewer,
        subject_person_id=owner.person_id,
        target_type="DeathReport",
        target_id=report.id,
    )
    return {
        "memorials_suspended": memorials_suspended,
        "invites_revoked": invites_revoked,
        "cancelled_jobs": cancelled_jobs,
        "already_delivered_count": len(serializable_delivered),
        "already_delivered": serializable_delivered,
    }
