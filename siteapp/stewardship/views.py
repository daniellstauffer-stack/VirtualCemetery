"""Views for steward invitations, steward workspace, death reporting, staff verification desk, and public disputes."""
from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from siteapp.accounts.models import User, record_audit
from siteapp.accounts.views import has_recent_mfa
from siteapp.integrations.email_provider import send_transactional_email
from siteapp.planning.models import LifePlan, PlanMemory

from .forms import DeathReportForm, DisputeAppealForm, StaffDecisionForm, StewardInviteForm
from .models import DeathReport, DisputeAppeal, StewardAssignment, VerificationDecision
from .services import approve_death_report, is_active_steward_for, reverse_death_report


@login_required
def manage_stewards_view(request):
    """Owner manages primary & backup stewards ('the person who manages my memorial')."""
    form = StewardInviteForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        # Replacing or adding a steward is a high-impact action — require fresh MFA if already has active steward
        has_existing = StewardAssignment.objects.filter(
            owner=request.user,
            status__in=[StewardAssignment.Status.INVITED, StewardAssignment.Status.ACCEPTED],
        ).exists()
        if has_existing and not has_recent_mfa(request):
            messages.warning(
                request,
                "Please complete a quick multi-factor check before changing your steward designation.",
            )
            return redirect(f"{reverse('accounts:mfa')}?next={reverse('stewardship:manage')}")

        assignment = form.save(commit=False)
        assignment.owner = request.user
        assignment.save()
        record_audit(
            action="steward.invited",
            summary=f"Invited {assignment.get_role_display()} (expires {assignment.expires_at:%Y-%m-%d}).",
            actor=request.user,
            subject_person_id=request.user.person_id,
            target_type="StewardAssignment",
            target_id=assignment.id,
        )
        accept_url = request.build_absolute_uri(
            reverse("stewardship:respond_invite", kwargs={"token": assignment.invite_token})
        )
        send_transactional_email(
            to_email=assignment.invitee_email,
            to_name=assignment.invitee_name,
            subject=f"{request.user.full_display_name} invited you to manage their Virtual Cemetery memorial",
            body=(
                f"Hello {assignment.invitee_name},\n\n"
                f"{request.user.full_display_name} has invited you to serve as their {assignment.get_role_display()} "
                "on Virtual Cemetery. This role lets you care for their memorial after a verified death within the "
                "choices they set. It grants no legal authority over their estate.\n\n"
                f"Review and accept or decline before {assignment.expires_at:%B %d, %Y}:\n{accept_url}\n"
            ),
            idempotency_key=f"steward-invite-{assignment.id}",
        )
        messages.success(
            request,
            f"Steward invitation created for {assignment.invitee_name}. It expires in 14 days.",
        )
        return redirect("stewardship:manage")

    assignments = StewardAssignment.objects.filter(owner=request.user)
    incoming_invites = StewardAssignment.objects.filter(
        invitee_email__iexact=request.user.email,
        status=StewardAssignment.Status.INVITED,
    ).select_related("owner")
    my_stewardships = StewardAssignment.objects.filter(
        steward_user=request.user,
        status=StewardAssignment.Status.ACCEPTED,
        revoked_at__isnull=True,
    ).select_related("owner")

    return render(
        request,
        "stewardship/manage.html",
        {
            "form": form,
            "assignments": assignments,
            "incoming_invites": incoming_invites,
            "my_stewardships": my_stewardships,
            "mfa_fresh": has_recent_mfa(request),
        },
    )


@login_required
@require_POST
def revoke_steward_view(request, assignment_id):
    """Revoking a steward immediately ends access across existing sessions and old links."""
    assignment = get_object_or_404(StewardAssignment, id=assignment_id, owner=request.user)
    if not has_recent_mfa(request):
        messages.warning(request, "Please confirm your identity with MFA before revoking a steward.")
        return redirect(f"{reverse('accounts:mfa')}?next={reverse('stewardship:manage')}")
    assignment.revoke()
    record_audit(
        action="steward.revoked",
        summary=f"Revoked {assignment.get_role_display()} immediately.",
        actor=request.user,
        subject_person_id=request.user.person_id,
        target_type="StewardAssignment",
        target_id=assignment.id,
    )
    messages.success(
        request,
        f"{assignment.invitee_name}'s steward access has been revoked immediately.",
    )
    return redirect("stewardship:manage")


@login_required
def respond_invite_view(request, token):
    """Intended verified recipient accepts or declines a steward invitation."""
    assignment = get_object_or_404(StewardAssignment.objects.select_related("owner"), invite_token=token)

    if not assignment.is_invitation_redeemable:
        return render(
            request,
            "stewardship/invite_unavailable.html",
            {"assignment": assignment},
            status=410,
        )

    email_matches = request.user.email.lower() == assignment.invitee_email.lower()
    if request.method == "POST":
        decision = request.POST.get("decision")
        if not email_matches or not request.user.email_verified:
            messages.error(
                request,
                "This invitation can only be accepted by a verified account matching the invited email address.",
            )
            return redirect("stewardship:respond_invite", token=token)

        if decision == "accept":
            assignment.steward_user = request.user
            assignment.status = StewardAssignment.Status.ACCEPTED
            assignment.accepted_at = timezone.now()
            assignment.save(update_fields=["steward_user", "status", "accepted_at"])
            record_audit(
                action="steward.accepted",
                summary=f"{assignment.get_role_display()} accepted invitation.",
                actor=request.user,
                subject_person_id=assignment.owner.person_id,
                target_type="StewardAssignment",
                target_id=assignment.id,
            )
            messages.success(
                request,
                f"You accepted the role of {assignment.get_role_display()} for {assignment.owner.full_display_name}.",
            )
            return redirect("stewardship:workspace", owner_person_id=assignment.owner.person_id)
        elif decision == "decline":
            assignment.status = StewardAssignment.Status.DECLINED
            assignment.save(update_fields=["status"])
            record_audit(
                action="steward.declined",
                summary=f"{assignment.get_role_display()} declined invitation.",
                actor=request.user,
                subject_person_id=assignment.owner.person_id,
                target_type="StewardAssignment",
                target_id=assignment.id,
            )
            messages.info(request, "You have declined this steward invitation.")
            return redirect("stewardship:manage")

    return render(
        request,
        "stewardship/respond_invite.html",
        {"assignment": assignment, "email_matches": email_matches},
    )


@login_required
def steward_workspace_view(request, owner_person_id):
    """Screen showing a steward exactly what they can and cannot read right now."""
    owner = get_object_or_404(User, person_id=owner_person_id)
    if not is_active_steward_for(request.user, owner):
        raise Http404("You are not an active steward for this account.")

    assignment = StewardAssignment.objects.filter(
        owner=owner,
        steward_user=request.user,
        status=StewardAssignment.Status.ACCEPTED,
        revoked_at__isnull=True,
    ).first()
    plan = LifePlan.objects.filter(owner=owner).first()
    reports = DeathReport.objects.filter(subject_owner=owner)

    # Strictly enforce: while owner is living, steward sees NO private wishes or unreleased memories!
    released_memories = []
    if owner.is_deceased_verified and plan:
        released_memories = plan.memories.exclude(audience=PlanMemory.Audience.PRIVATE_ONLY)

    from siteapp.memorials.models import Memorial

    memorial = Memorial.objects.filter(owner=owner).first()

    resp = render(
        request,
        "stewardship/workspace.html",
        {
            "owner": owner,
            "assignment": assignment,
            "plan": plan,
            "released_memories": released_memories,
            "reports": reports,
            "memorial": memorial,
        },
    )
    resp.vc_restricted = True
    return resp


@login_required
def submit_death_report_view(request, owner_person_id):
    """Steward files a private death report with minimum supporting evidence."""
    owner = get_object_or_404(User, person_id=owner_person_id)
    if not is_active_steward_for(request.user, owner):
        raise Http404("Only an active steward may file a steward death report here.")

    form = DeathReportForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        report = form.save(commit=False)
        report.subject_owner = owner
        report.submitted_by = request.user
        report.status = DeathReport.Status.SUBMITTED
        report.save()
        record_audit(
            action="death_report.submitted",
            summary="Private death report submitted for staff verification. No notices sent.",
            actor=request.user,
            subject_person_id=owner.person_id,
            target_type="DeathReport",
            target_id=report.id,
        )
        messages.success(
            request,
            "Your report has been received privately by our verification team. "
            "No memorial pages have changed and no invitations have been sent. "
            "A trained reviewer will check independent evidence and attempt to reach the account owner first.",
        )
        return redirect("stewardship:workspace", owner_person_id=owner.person_id)

    return render(
        request,
        "stewardship/submit_report.html",
        {"owner": owner, "form": form},
    )


def _require_staff_reviewer_with_mfa(request):
    if not request.user.is_authenticated or not request.user.is_verified_reviewer:
        raise Http404("Not found.")
    if not has_recent_mfa(request):
        return redirect(f"{reverse('accounts:mfa')}?next={request.get_full_path()}")
    return None


@login_required
def staff_desk_view(request):
    """Restricted staff verification desk. Requires staff reviewer role + MFA."""
    gate = _require_staff_reviewer_with_mfa(request)
    if gate:
        return gate

    pending_reports = DeathReport.objects.filter(
        status__in=[
            DeathReport.Status.SUBMITTED,
            DeathReport.Status.CHALLENGE_WINDOW,
            DeathReport.Status.CONFLICT_PAUSED,
        ]
    ).select_related("subject_owner", "submitted_by", "assigned_reviewer")
    closed_reports = DeathReport.objects.filter(
        status__in=[
            DeathReport.Status.APPROVED,
            DeathReport.Status.REJECTED,
            DeathReport.Status.REVERSED,
        ]
    ).select_related("subject_owner", "assigned_reviewer")[:25]
    open_disputes = DisputeAppeal.objects.filter(status=DisputeAppeal.Status.OPEN)

    resp = render(
        request,
        "stewardship/staff_desk.html",
        {
            "pending_reports": pending_reports,
            "closed_reports": closed_reports,
            "open_disputes": open_disputes,
        },
    )
    resp.vc_restricted = True
    return resp


@login_required
def staff_case_detail_view(request, report_id):
    gate = _require_staff_reviewer_with_mfa(request)
    if gate:
        return gate

    report = get_object_or_404(
        DeathReport.objects.select_related("subject_owner", "submitted_by", "assigned_reviewer", "second_reviewer"),
        id=report_id,
    )
    record_audit(
        action="staff.case_viewed",
        summary="Staff reviewer opened death-verification case.",
        actor=request.user,
        subject_person_id=report.subject_owner.person_id,
        target_type="DeathReport",
        target_id=report.id,
    )
    decision_form = StaffDecisionForm(request.POST or None)

    if request.method == "POST":
        action = request.POST.get("staff_action", "")
        if action == "assign":
            report.assigned_reviewer = request.user
            report.save(update_fields=["assigned_reviewer", "updated_at"])
            VerificationDecision.objects.create(
                report=report,
                reviewer=request.user,
                action=VerificationDecision.Action.ASSIGNED,
                reason="Reviewer claimed case for verification.",
            )
            messages.success(request, "Case assigned to you.")
            return redirect("stewardship:staff_case", report_id=report.id)

        elif action == "check_evidence":
            report.independent_evidence_checked = True
            if not report.assigned_reviewer:
                report.assigned_reviewer = request.user
            report.save(update_fields=["independent_evidence_checked", "assigned_reviewer", "updated_at"])
            VerificationDecision.objects.create(
                report=report,
                reviewer=request.user,
                action=VerificationDecision.Action.EVIDENCE_CHECKED,
                reason=request.POST.get("reason", "").strip() or "Independent evidence verified per launch policy.",
            )
            messages.success(request, "Independent evidence check recorded.")
            return redirect("stewardship:staff_case", report_id=report.id)

        elif action == "send_challenge":
            owner = report.subject_owner
            report.owner_challenge_sent_at = timezone.now()
            report.owner_challenge_channel = owner.email + (
                f" / {owner.verified_phone_hint}" if owner.verified_phone_hint else ""
            )
            if report.status == DeathReport.Status.SUBMITTED:
                report.status = DeathReport.Status.CHALLENGE_WINDOW
            report.save(
                update_fields=["owner_challenge_sent_at", "owner_challenge_channel", "status", "updated_at"]
            )
            dispute_url = request.build_absolute_uri(reverse("stewardship:dispute"))
            send_transactional_email(
                to_email=owner.email,
                to_name=owner.full_display_name,
                subject="Urgent: Someone reported your passing on Virtual Cemetery — please reply if this is an error",
                body=(
                    f"Hello {owner.full_display_name},\n\n"
                    "We received a death report for your Virtual Cemetery account. "
                    "Nothing has been published and no family invitations have been sent.\n\n"
                    f"If you are living and this report is an error, challenge it immediately here (no sign-in required):\n{dispute_url}\n"
                ),
                idempotency_key=f"owner-challenge-{report.id}",
            )
            VerificationDecision.objects.create(
                report=report,
                reviewer=request.user,
                action=VerificationDecision.Action.CHALLENGE_SENT,
                reason="Challenge outreach sent to owner's verified contact channel.",
            )
            messages.success(request, "Owner challenge outreach recorded and sent.")
            return redirect("stewardship:staff_case", report_id=report.id)

        elif action == "pause_conflict" and decision_form.is_valid():
            report.status = DeathReport.Status.CONFLICT_PAUSED
            report.save(update_fields=["status", "updated_at"])
            VerificationDecision.objects.create(
                report=report,
                reviewer=request.user,
                action=VerificationDecision.Action.CONFLICT_PAUSED,
                reason=decision_form.cleaned_data["reason"],
            )
            messages.warning(request, "Case paused for a second independent reviewer.")
            return redirect("stewardship:staff_case", report_id=report.id)

        elif action == "approve" and decision_form.is_valid():
            try:
                approve_death_report(report, request.user, decision_form.cleaned_data["reason"])
                messages.success(
                    request,
                    "Death verification approved atomically. The accepted steward may now prepare and preview the memorial.",
                )
            except ValueError as exc:
                messages.error(request, str(exc))
            return redirect("stewardship:staff_case", report_id=report.id)

        elif action == "reject" and decision_form.is_valid():
            report.status = DeathReport.Status.REJECTED
            report.save(update_fields=["status", "updated_at"])
            VerificationDecision.objects.create(
                report=report,
                reviewer=request.user,
                action=VerificationDecision.Action.REJECTED,
                reason=decision_form.cleaned_data["reason"],
            )
            record_audit(
                action="verification.rejected",
                summary="Death report rejected by reviewer.",
                actor=request.user,
                subject_person_id=report.subject_owner.person_id,
                target_type="DeathReport",
                target_id=report.id,
            )
            messages.info(request, "Death report rejected and closed.")
            return redirect("stewardship:staff_case", report_id=report.id)

        elif action == "reverse" and decision_form.is_valid():
            summary = reverse_death_report(report, request.user, decision_form.cleaned_data["reason"])
            messages.warning(
                request,
                f"Approval reversed. Owner restored; {summary['memorials_suspended']} memorial(s) suspended, "
                f"{summary['invites_revoked']} invite(s) revoked, {summary['cancelled_jobs']} unsent job(s) cancelled, "
                f"{summary['already_delivered_count']} already-delivered notice(s) logged for correction.",
            )
            return redirect("stewardship:staff_case", report_id=report.id)

    decisions = report.decisions.select_related("reviewer").all()
    disputes = report.disputes.all()
    resp = render(
        request,
        "stewardship/staff_case.html",
        {
            "report": report,
            "decisions": decisions,
            "disputes": disputes,
            "decision_form": decision_form,
        },
    )
    resp.vc_restricted = True
    return resp


@login_required
def staff_evidence_download_view(request, report_id):
    """Restricted evidence file download: ONLY assigned reviewer (or second reviewer) with MFA."""
    gate = _require_staff_reviewer_with_mfa(request)
    if gate:
        return gate

    report = get_object_or_404(DeathReport, id=report_id)
    is_assigned = (
        report.assigned_reviewer_id == request.user.id
        or report.second_reviewer_id == request.user.id
    )
    if not is_assigned:
        raise Http404("Only an assigned case reviewer may access case evidence.")
    if not report.evidence_file or not report.evidence_file.name:
        raise Http404("No evidence file attached or file has been purged.")

    record_audit(
        action="staff.evidence_accessed",
        summary="Assigned reviewer accessed case evidence file.",
        actor=request.user,
        subject_person_id=report.subject_owner.person_id,
        target_type="DeathReport",
        target_id=report.id,
    )
    resp = FileResponse(report.evidence_file.open("rb"))
    resp["Cache-Control"] = "private, no-store"
    resp["X-Robots-Tag"] = "noindex, nofollow"
    return resp


def dispute_appeal_view(request):
    """Public unauthenticated appeal/dispute route so a living owner or family
    member can challenge a mistaken report without signing into the disputed account.
    """
    form = DisputeAppealForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        dispute = form.save(commit=False)
        # Try linking to any active report by owner email
        matched_report = (
            DeathReport.objects.filter(
                subject_owner__email__iexact=dispute.subject_email_or_name.strip()
            )
            .exclude(status=DeathReport.Status.REJECTED)
            .first()
        )
        if matched_report:
            dispute.related_report = matched_report
            # Automatically pause an in-progress case when a competing claim / dispute arrives!
            if matched_report.status in (
                DeathReport.Status.SUBMITTED,
                DeathReport.Status.CHALLENGE_WINDOW,
            ):
                matched_report.status = DeathReport.Status.CONFLICT_PAUSED
                matched_report.save(update_fields=["status", "updated_at"])
        dispute.save()
        record_audit(
            action="dispute.submitted",
            summary="Urgent dispute or mistaken-report challenge submitted.",
            actor=request.user if request.user.is_authenticated else None,
            subject_person_id=matched_report.subject_owner.person_id if matched_report else None,
            target_type="DisputeAppeal",
            target_id=dispute.id,
        )
        messages.success(
            request,
            "Your dispute has been logged with high priority. Any pending case has been paused immediately "
            "and a reviewer will contact you directly.",
        )
        return redirect("stewardship:dispute")

    return render(request, "stewardship/dispute.html", {"form": form})
