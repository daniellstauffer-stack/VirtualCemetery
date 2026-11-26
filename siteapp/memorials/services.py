"""Permission checks and snapshot publishing services for Memorials."""
from __future__ import annotations

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from siteapp.accounts.models import User, record_audit
from siteapp.planning.models import LifePlan, PlanMemory
from siteapp.stewardship.services import is_active_steward_for

from .models import Memorial, MemorialInvite, MemorialRelationship, PublishedMemory


def can_manage_memorial(user: User | None, memorial: Memorial) -> bool:
    """Owner (while living) or active accepted steward (after verified death) may manage."""
    if not user or not user.is_authenticated:
        return False
    if memorial.owner_id and user.id == memorial.owner_id:
        return True
    if memorial.owner_id and memorial.owner.is_deceased_verified:
        return is_active_steward_for(user, memorial.owner)
    if memorial.is_family_created and memorial.published_by_id == user.id:
        return True
    return False


def can_view_memorial(user: User | None, memorial: Memorial) -> bool:
    """Recheck live access on every view, media request, search, and relationship lookup."""
    if memorial.status == Memorial.Status.SUSPENDED:
        return bool(
            user
            and user.is_authenticated
            and (user.id == memorial.owner_id or user.is_verified_reviewer)
        )

    if memorial.status == Memorial.Status.DRAFT:
        return can_manage_memorial(user, memorial)

    # Published memorial
    if memorial.audience == Memorial.Audience.PUBLIC:
        return True

    # Invited-only published memorial
    if not user or not user.is_authenticated:
        return False
    if can_manage_memorial(user, memorial):
        return True
    if user.is_verified_reviewer:
        return True

    return MemorialInvite.objects.filter(
        memorial=memorial,
        revoked_at__isnull=True,
    ).filter(
        Q(redeemed_by=user)
        | Q(intended_email__iexact=user.email, expires_at__gte=timezone.now())
    ).exists()


def visible_relationships_for(memorial: Memorial, viewer: User | None) -> list[dict]:
    """Return accepted relationships ONLY when viewer has permission to see BOTH endpoints."""
    if not can_view_memorial(viewer, memorial):
        return []

    qs = MemorialRelationship.objects.filter(
        status=MemorialRelationship.Status.ACCEPTED,
        from_approved=True,
        to_approved=True,
        withdrawn_at__isnull=True,
    ).filter(
        Q(from_memorial=memorial) | Q(to_memorial=memorial)
    ).select_related("from_memorial", "to_memorial")

    results = []
    for rel in qs:
        if rel.from_memorial_id == memorial.id:
            other = rel.to_memorial
            label = rel.label_from_to
        else:
            other = rel.from_memorial
            label = rel.label_to_from

        # Strict two-endpoint visibility check!
        if can_view_memorial(viewer, other):
            results.append(
                {
                    "relationship": rel,
                    "other_memorial": other,
                    "label": label,
                }
            )
    return results


@transaction.atomic
def publish_memorial_snapshot(
    *,
    owner: User,
    steward: User,
    selected_memory_ids: list[str],
    chosen_audience: str,
    allow_site_search: bool,
    steward_tribute: str = "",
) -> Memorial:
    """Create or update the separate approved Published Memorial snapshot from a verified owner's plan.

    Enforces:
    - Owner's death MUST be verified first.
    - Steward MUST be currently active (not revoked).
    - Audience cannot exceed owner's chosen ceiling.
    - Private memories (PRIVATE_ONLY / STEWARD_AFTER_DEATH) can NEVER be published.
    """
    if not owner.is_deceased_verified:
        raise PermissionError("Cannot publish a memorial until death verification is approved.")
    if not is_active_steward_for(steward, owner):
        raise PermissionError("Only an active accepted steward may publish this memorial.")

    plan = LifePlan.objects.get(owner=owner)

    # Enforce owner's audience ceiling!
    if plan.memorial_audience_ceiling == LifePlan.MemorialAudienceCeiling.INVITED_ONLY:
        effective_audience = Memorial.Audience.INVITED_ONLY
        effective_search = False
    else:
        effective_audience = (
            Memorial.Audience.PUBLIC
            if chosen_audience == Memorial.Audience.PUBLIC
            else Memorial.Audience.INVITED_ONLY
        )
        effective_search = bool(
            allow_site_search
            and plan.allow_site_search
            and effective_audience == Memorial.Audience.PUBLIC
        )

    memorial, _ = Memorial.objects.get_or_create(
        owner=owner,
        defaults={
            "person_id": owner.person_id,
            "full_name": plan.display_memorial_name,
        },
    )
    memorial.person_id = owner.person_id
    memorial.full_name = plan.display_memorial_name
    memorial.birth_year = plan.birth_year
    memorial.death_year = (
        owner.death_verified_at.year if owner.death_verified_at else timezone.now().year
    )
    memorial.biography = plan.biography_draft
    memorial.steward_tribute = steward_tribute.strip()
    memorial.steward_tribute_author = steward.full_display_name if steward_tribute.strip() else ""
    memorial.portrait_storage_path = plan.portrait_file.name if plan.portrait_file else ""
    memorial.portrait_static_asset = plan.portrait_static_asset
    memorial.portrait_alt_text = plan.portrait_alt_text or f"Portrait of {plan.display_memorial_name}"
    memorial.audience = effective_audience
    memorial.allow_site_search = effective_search
    memorial.guestbook_requires_approval = plan.guestbook_requires_approval
    memorial.status = Memorial.Status.PUBLISHED
    memorial.published_by = steward
    memorial.published_at = memorial.published_at or timezone.now()
    memorial.save()

    # Rebuild published memories snapshot ONLY from owner-permitted memories
    allowed_audiences = [PlanMemory.Audience.INVITED_MEMORIAL, PlanMemory.Audience.PUBLIC_MEMORIAL]
    if effective_audience == Memorial.Audience.PUBLIC:
        allowed_audiences = [PlanMemory.Audience.PUBLIC_MEMORIAL]

    eligible = PlanMemory.objects.filter(
        plan=plan,
        id__in=selected_memory_ids,
        audience__in=allowed_audiences,
    )

    memorial.published_memories.all().delete()
    for idx, pm in enumerate(eligible):
        display_path = pm.photo_display.name if pm.photo_display else (pm.photo_original.name if pm.photo_original else "")
        PublishedMemory.objects.create(
            memorial=memorial,
            source_plan_memory_id=pm.id,
            title=pm.title,
            year_taken=pm.year_taken,
            story=pm.story,
            alt_text=pm.alt_text,
            display_media_path=display_path,
            static_sample_image=pm.static_sample_image,
            display_order=idx,
        )

    record_audit(
        action="memorial.published",
        summary=f"Published memorial snapshot with {eligible.count()} memory item(s), audience={effective_audience}.",
        actor=steward,
        subject_person_id=owner.person_id,
        target_type="Memorial",
        target_id=memorial.id,
    )
    return memorial
