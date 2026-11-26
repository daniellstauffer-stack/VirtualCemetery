"""Authentication, step-up MFA, profile settings, and explicit access-grant views."""
from __future__ import annotations

from datetime import timedelta
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from .forms import AccessGrantForm, AccountProfileForm, LoginForm, RegistrationForm, StepUpMFAForm
from .models import AccessGrant, AuditEvent, User, record_audit

MFA_VALIDITY_MINUTES = 20


def has_recent_mfa(request) -> bool:
    """Return True if the current session passed step-up MFA recently."""
    ts = request.session.get("mfa_verified_at")
    if not ts:
        return False
    try:
        verified_dt = timezone.datetime.fromisoformat(ts)
        if timezone.is_naive(verified_dt):
            verified_dt = timezone.make_aware(verified_dt)
    except ValueError:
        return False
    return timezone.now() - verified_dt <= timedelta(minutes=MFA_VALIDITY_MINUTES)


def register_view(request):
    if request.user.is_authenticated:
        return redirect("planning:dashboard")
    form = RegistrationForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = User.objects.create_user(
            email=form.cleaned_data["email"],
            password=form.cleaned_data["password"],
            display_name=form.cleaned_data["display_name"],
            jurisdiction=form.cleaned_data["jurisdiction"],
            # In local emulator mode we verify immediately after showing notice;
            # in production Identity Platform sends a verification email first.
            email_verified=settings.LOCAL_AUTH_EMULATOR,
            mfa_enabled=True,
        )
        record_audit(
            action="account.registered",
            summary="New family account created.",
            actor=user,
            subject_person_id=user.person_id,
            target_type="User",
            target_id=user.person_id,
        )
        login(request, user)
        messages.success(
            request,
            "Welcome to Virtual Cemetery. Everything inside My Plan stays private unless you choose to share it.",
        )
        return redirect("planning:dashboard")
    return render(request, "accounts/register.html", {"form": form})


def login_view(request):
    if request.user.is_authenticated:
        return redirect("planning:dashboard")
    form = LoginForm(request=request, data=request.POST or None)
    next_url = request.GET.get("next") or request.POST.get("next") or ""
    if request.method == "POST" and form.is_valid():
        user = form.user_cache
        login(request, user)
        record_audit(
            action="account.login",
            summary="Account signed in.",
            actor=user,
            subject_person_id=user.person_id,
        )
        if next_url and next_url.startswith("/"):
            return redirect(next_url)
        if user.is_verified_reviewer:
            return redirect("stewardship:staff_desk")
        return redirect("planning:dashboard")

    demo_accounts = []
    if settings.LOCAL_AUTH_EMULATOR:
        demo_accounts = [
            ("Arthur Pendelton (Owner / Grandfather)", "arthur@example.org", "PilotFamily2026!"),
            ("Clara Pendelton (Steward & Organizer)", "clara@example.org", "PilotFamily2026!"),
            ("Elena Pendelton (Family Visitor)", "elena@example.org", "PilotFamily2026!"),
            ("Hannah Brooks (Staff Site Reviewer)", "reviewer@example.org", "StaffReview2026!"),
        ]
    return render(
        request,
        "accounts/login.html",
        {"form": form, "next": next_url, "demo_accounts": demo_accounts},
    )


@require_POST
def logout_view(request):
    if request.user.is_authenticated:
        record_audit(
            action="account.logout",
            summary="Account signed out.",
            actor=request.user,
            subject_person_id=request.user.person_id,
        )
    logout(request)
    messages.info(request, "You have signed out safely.")
    return redirect("home")


@login_required
def step_up_mfa_view(request):
    next_url = request.GET.get("next") or request.POST.get("next") or "/accounts/profile/"
    form = StepUpMFAForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        entered = form.cleaned_data["code"].strip()
        expected = request.user.mfa_demo_code if settings.LOCAL_AUTH_EMULATOR else ""
        if settings.LOCAL_AUTH_EMULATOR and entered == expected:
            request.session["mfa_verified_at"] = timezone.now().isoformat()
            record_audit(
                action="account.mfa_verified",
                summary="Step-up multi-factor verification completed.",
                actor=request.user,
                subject_person_id=request.user.person_id,
            )
            messages.success(request, "Identity check confirmed for the next 20 minutes.")
            return redirect(next_url if next_url.startswith("/") else "/accounts/profile/")
        form.add_error("code", "That verification code did not match. Please try again.")
    return render(
        request,
        "accounts/mfa_verify.html",
        {
            "form": form,
            "next": next_url,
            "demo_code": request.user.mfa_demo_code if settings.LOCAL_AUTH_EMULATOR else None,
        },
    )


@login_required
def profile_view(request):
    form = AccountProfileForm(request.POST or None, instance=request.user)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        request.session["text_scale"] = user.preferred_text_scale
        record_audit(
            action="account.profile_updated",
            summary="Account contact or accessibility preferences updated.",
            actor=user,
            subject_person_id=user.person_id,
        )
        messages.success(request, "Your account settings have been saved.")
        return redirect("accounts:profile")

    recent_audit = AuditEvent.objects.filter(subject_person_id=request.user.person_id)[:15]
    return render(
        request,
        "accounts/profile.html",
        {
            "form": form,
            "recent_audit": recent_audit,
            "mfa_fresh": has_recent_mfa(request),
            "identity_platform_project": settings.GCP_IDENTITY_PLATFORM_PROJECT_ID,
        },
    )


@login_required
def verify_email_view(request):
    if request.method == "POST":
        request.user.email_verified = True
        request.user.save(update_fields=["email_verified"])
        record_audit(
            action="account.email_verified",
            summary="Email address verified.",
            actor=request.user,
            subject_person_id=request.user.person_id,
        )
        messages.success(request, "Your email address is now verified.")
    return redirect("accounts:profile")


@login_required
def access_grants_view(request):
    """Owner manages explicit grants of private funeral instructions or contacts."""
    form = AccessGrantForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        grant = form.save(commit=False)
        grant.owner = request.user
        matched_user = User.objects.filter(email__iexact=grant.recipient_email).first()
        if matched_user:
            grant.recipient_user = matched_user
        grant.save()
        record_audit(
            action="grant.created",
            summary=f"Granted {grant.get_scope_display()} ({grant.get_release_timing_display()}).",
            actor=request.user,
            subject_person_id=request.user.person_id,
            target_type="AccessGrant",
            target_id=grant.id,
        )
        messages.success(request, "Access grant recorded. You can revoke it at any time.")
        return redirect("accounts:grants")

    outgoing = AccessGrant.objects.filter(owner=request.user)
    incoming = [
        g
        for g in AccessGrant.objects.filter(
            recipient_email__iexact=request.user.email, revoked_at__isnull=True
        ).select_related("owner")
        if g.is_currently_accessible_by(request.user)
    ]
    return render(
        request,
        "accounts/grants.html",
        {"form": form, "outgoing_grants": outgoing, "incoming_grants": incoming},
    )


@login_required
@require_POST
def revoke_grant_view(request, grant_id):
    grant = get_object_or_404(AccessGrant, id=grant_id, owner=request.user)
    grant.revoke()
    record_audit(
        action="grant.revoked",
        summary=f"Revoked {grant.get_scope_display()} grant.",
        actor=request.user,
        subject_person_id=request.user.person_id,
        target_type="AccessGrant",
        target_id=grant.id,
    )
    messages.success(request, "Access grant revoked immediately.")
    return redirect("accounts:grants")


@require_POST
def set_text_scale_view(request):
    scale = request.POST.get("scale", "normal")
    if scale in ("normal", "large", "xlarge"):
        request.session["text_scale"] = scale
        if request.user.is_authenticated:
            request.user.preferred_text_scale = scale
            request.user.save(update_fields=["preferred_text_scale"])
    next_url = request.POST.get("next") or request.META.get("HTTP_REFERER") or "/"
    return redirect(next_url if next_url.startswith("/") else "/")
