"""Template context processor exposing site metadata, accessibility scale, and role badges."""
from __future__ import annotations

from django.conf import settings


def site_context(request):
    text_scale = request.session.get("text_scale")
    if not text_scale and request.user.is_authenticated:
        text_scale = getattr(request.user, "preferred_text_scale", "normal")
    text_scale = text_scale if text_scale in ("normal", "large", "xlarge") else "normal"

    pending_steward_invites = 0
    pending_review_cases = 0
    if request.user.is_authenticated:
        from siteapp.stewardship.models import DeathReport, StewardAssignment

        pending_steward_invites = StewardAssignment.objects.filter(
            invitee_email__iexact=request.user.email,
            status=StewardAssignment.Status.INVITED,
        ).count()
        if request.user.is_verified_reviewer:
            pending_review_cases = DeathReport.objects.filter(
                status__in=[
                    DeathReport.Status.SUBMITTED,
                    DeathReport.Status.CHALLENGE_WINDOW,
                    DeathReport.Status.CONFLICT_PAUSED,
                ]
            ).count()

    return {
        "SITE_OPERATOR_NAME": settings.OPERATOR_NAME,
        "SITE_SUPPORT_EMAIL": settings.SUPPORT_EMAIL,
        "PILOT_JURISDICTION": settings.PILOT_JURISDICTION,
        "LOCAL_AUTH_EMULATOR": settings.LOCAL_AUTH_EMULATOR,
        "FACEBOOK_LOGIN_ENABLED": settings.FACEBOOK_LOGIN_ENABLED,
        "STRIPE_ENABLED": settings.STRIPE_ENABLED,
        "TEXT_SCALE": text_scale,
        "PENDING_STEWARD_INVITES_COUNT": pending_steward_invites,
        "PENDING_REVIEW_CASES_COUNT": pending_review_cases,
    }
