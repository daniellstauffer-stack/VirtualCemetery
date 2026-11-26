"""Seed fictional family pilot data matching the Virtual Cemetery README walkthrough.

Uses ONLY fictional names and verified royalty-free images from static/images/.
Safe to run multiple times (idempotent).
"""
from __future__ import annotations

from decimal import Decimal
from django.core.management.base import BaseCommand
from django.utils import timezone

from siteapp.accounts.models import AccessGrant, User
from siteapp.events.models import FuneralContact
from siteapp.integrations.models import DirectoryProvider
from siteapp.memorials.models import (
    GuestbookEntry,
    Memorial,
    MemorialRelationship,
    PublishedMemory,
)
from siteapp.planning.models import LifePlan, PlanMemory, WishesWorksheet
from siteapp.stewardship.models import StewardAssignment


class Command(BaseCommand):
    help = "Populate fictional pilot family records and curated local directory providers."

    def handle(self, *args, **options):
        # 1. Fictional family accounts (grandfather Arthur, daughter/steward Clara, granddaughter Elena, staff reviewer Hannah)
        arthur, _ = User.objects.get_or_create(
            email="arthur@example.org",
            defaults={
                "username": "arthur@example.org",
                "display_name": "Arthur Pendelton",
                "email_verified": True,
                "verified_phone_hint": "(503) 555-0142 (fictional)",
                "jurisdiction": "Oregon, United States",
                "mfa_enabled": True,
            },
        )
        arthur.set_password("PilotFamily2026!")
        arthur.save()

        clara, _ = User.objects.get_or_create(
            email="clara@example.org",
            defaults={
                "username": "clara@example.org",
                "display_name": "Clara Pendelton",
                "email_verified": True,
                "jurisdiction": "Oregon, United States",
                "mfa_enabled": True,
            },
        )
        clara.set_password("PilotFamily2026!")
        clara.save()

        elena, _ = User.objects.get_or_create(
            email="elena@example.org",
            defaults={
                "username": "elena@example.org",
                "display_name": "Elena Pendelton",
                "email_verified": True,
                "jurisdiction": "Oregon, United States",
                "mfa_enabled": True,
            },
        )
        elena.set_password("PilotFamily2026!")
        elena.save()

        reviewer, _ = User.objects.get_or_create(
            email="reviewer@example.org",
            defaults={
                "username": "reviewer@example.org",
                "display_name": "Hannah Brooks",
                "email_verified": True,
                "is_staff": True,
                "is_verified_reviewer": True,
                "mfa_enabled": True,
            },
        )
        reviewer.set_password("StaffReview2026!")
        reviewer.save()

        # 2. Arthur's private Life Plan (living grandfather from README)
        plan, _ = LifePlan.objects.get_or_create(
            owner=arthur,
            defaults={
                "memorial_preferred_name": "Arthur H. Pendelton",
                "birth_year": 1944,
                "biography_draft": (
                    "Born in Eugene and raised among Douglas firs, I spent forty-one years as a cabinetmaker "
                    "and weekend boatbuilder. My proudest work was never in the shop—it was teaching my daughter "
                    "Clara how to read the tides and watching my granddaughter Elena learn to sketch in the garden."
                ),
                "portrait_static_asset": "portrait-arthur.jpg",
                "portrait_alt_text": "Warm close-up portrait of Arthur Pendelton wearing round glasses.",
                "disposition_preference": LifePlan.DispositionChoice.GREEN_BURIAL,
                "disposition_notes": "Simple pine box in a quiet woodland meadow near the Willamette Valley. No embalming.",
                "service_wishes": "Keep the gathering small and outdoors if the rain holds off. Play Schubert's Trio in E-flat and serve strong coffee.",
                "emergency_contacts": "Clara Pendelton (Daughter) — (503) 555-0199 (fictional)\nDr. Miriam Okafor (Primary physician) — (503) 555-0114 (fictional)",
                "important_document_locations": "Signed will and house deed are in the green fireproof box on the top closet shelf in the study. Estate attorney is Riverbend Elder Law in Portland.",
                "memorial_audience_ceiling": LifePlan.MemorialAudienceCeiling.INVITED_ONLY,
                "allow_site_search": False,
                "guestbook_requires_approval": True,
            },
        )

        # Sample memories in Arthur's private plan (demonstrating distinct audience controls)
        if not plan.memories.exists():
            PlanMemory.objects.create(
                plan=plan,
                title="Autumn mornings by the willow boat",
                year_taken="1998",
                story=(
                    "Every October, Evelyn and I drove out before sunrise to row along the quiet cove. "
                    "We brought wool blankets and a thermos of apple cider and never said a word until the mist cleared."
                ),
                alt_text="A wooden rowboat resting beside calm water under drooping willow branches.",
                static_sample_image="memory-lake.jpg",
                audience=PlanMemory.Audience.INVITED_MEMORIAL,
                owner_confirmed_rights=True,
                source_label="Added directly",
            )
            PlanMemory.objects.create(
                plan=plan,
                title="Forty years at the cedar workbench",
                year_taken="2014",
                story=(
                    "The old shop window still catches afternoon light just the way it did in 1973. "
                    "Every chisel on that bench was sharpened by hand."
                ),
                alt_text="Hand tools, jars, and woodworking supplies resting on a sunlit rustic workbench beside a window.",
                static_sample_image="memory-woodshop.jpg",
                audience=PlanMemory.Audience.INVITED_MEMORIAL,
                owner_confirmed_rights=True,
                source_label="Added directly",
            )
            PlanMemory.objects.create(
                plan=plan,
                title="Private letter to Clara (Steward only after death)",
                year_taken="2025",
                story="Clara, thank you for looking after the shop tools. Please give the brass compass to Elena on her graduation.",
                alt_text="Private written note from Arthur to his daughter Clara.",
                audience=PlanMemory.Audience.STEWARD_AFTER_DEATH,
                owner_confirmed_rights=True,
                source_label="Added directly",
            )
            PlanMemory.objects.create(
                plan=plan,
                title="Personal journal reflection (Only me)",
                year_taken="2026",
                story="A private reflection I am keeping strictly for myself and never releasing.",
                alt_text="Private personal journal entry.",
                audience=PlanMemory.Audience.PRIVATE_ONLY,
                owner_confirmed_rights=True,
                source_label="Added directly",
            )

        # Arthur's Draft My Wishes worksheet
        WishesWorksheet.objects.get_or_create(
            owner=arthur,
            defaults={
                "jurisdiction": "Oregon, United States",
                "dependants_summary": "No minor dependants. Barnaby (senior golden retriever) — Clara has agreed to care for him.",
                "asset_categories": "Primary residence (paid off), modest IRA retirement savings, woodworking tools & cedar skiff.",
                "intended_gifts": "Handcrafted cherry bookshelf to Elena; brass marine compass to Elena; garden tools to local community garden.",
                "executor_preferences": "Primary: Clara Pendelton. Alternate: Thomas Pendelton (nephew).",
                "questions_for_counsel": "Confirm transfer-on-death deed rules in Oregon and verify witnesses needed for updated healthcare directive.",
            },
        )

        # Clara designated & accepted as Arthur's Primary Steward + Funeral Organizer
        StewardAssignment.objects.get_or_create(
            owner=arthur,
            invitee_email=clara.email,
            defaults={
                "role": StewardAssignment.Role.PRIMARY,
                "invitee_name": clara.full_display_name,
                "steward_user": clara,
                "can_organize_funeral": True,
                "status": StewardAssignment.Status.ACCEPTED,
                "accepted_at": timezone.now(),
            },
        )

        # Explicit grant so Clara can view burial wishes after verified death
        AccessGrant.objects.get_or_create(
            owner=arthur,
            recipient_email=clara.email,
            scope=AccessGrant.Scope.FUNERAL_INSTRUCTIONS,
            defaults={
                "recipient_user": clara,
                "release_timing": AccessGrant.ReleaseTiming.AFTER_VERIFIED_DEATH,
                "note_to_recipient": "For organizing the woodland gathering when the time comes.",
            },
        )

        # Arthur's private funeral contact list
        for name, email, rel in [
            ("Elena Pendelton", "elena@example.org", "Granddaughter"),
            ("Thomas Pendelton", "thomas.pendelton@example.org", "Nephew"),
            ("Nora Lindholm", "nora.lindholm@example.org", "Longtime neighbor & friend"),
        ]:
            FuneralContact.objects.get_or_create(
                owner=arthur,
                email=email,
                defaults={"full_name": name, "relationship": rel, "source": "Manual entry"},
            )

        # 3. Sample Published Opt-In Public Memorials (so visitors see the serene memorial experience immediately)
        evelyn, created_ev = Memorial.objects.get_or_create(
            slug="evelyn-pendelton-1946",
            defaults={
                "full_name": "Evelyn Rose Pendelton",
                "birth_year": 1946,
                "death_year": 2023,
                "biography": (
                    "Evelyn taught botanical illustration for thirty years and believed every neighborhood "
                    "deserved climbing roses along its garden walls. She knew the Latin name of every fern "
                    "in the Coast Range, baked sourdough every Sunday morning, and left notebooks filled "
                    "with pressed leaves for her grandchildren."
                ),
                "steward_tribute": (
                    "Mom, your roses still bloom every June by the garden gate. Thank you for teaching us "
                    "to slow down, notice the light on the water, and leave things kinder than we found them."
                ),
                "steward_tribute_author": "Clara Pendelton",
                "portrait_static_asset": "portrait-evelyn.jpg",
                "portrait_alt_text": "Warm portrait of Evelyn Pendelton smiling with glasses.",
                "status": Memorial.Status.PUBLISHED,
                "audience": Memorial.Audience.PUBLIC,
                "allow_site_search": True,
                "guestbook_open": True,
                "guestbook_requires_approval": True,
                "published_by": clara,
                "published_at": timezone.now(),
            },
        )
        if created_ev:
            PublishedMemory.objects.create(
                memorial=evelyn,
                title="Climbing roses on the old brick garden wall",
                year_taken="2019",
                story="Evelyn tended these pale pink climbing roses for twenty summers, sketching each bloom in watercolor before the bees arrived.",
                alt_text="Pale pink climbing roses blooming atop a weathered red brick garden pier.",
                static_sample_image="memory-garden-rose.jpg",
                display_order=1,
            )
            PublishedMemory.objects.create(
                memorial=evelyn,
                title="Early days on the garden bench",
                year_taken="1968",
                story="Our favorite photograph from the summer after the wedding, sitting on the cedar bench behind the conservatory.",
                alt_text="Vintage black-and-white photograph of a smiling couple seated together on a wooden garden bench.",
                static_sample_image="memory-family-bench.jpg",
                display_order=2,
            )
            PublishedMemory.objects.create(
                memorial=evelyn,
                title="Morning rowboat under the willows",
                year_taken="2004",
                story="Evelyn's favorite quiet spot to sketch water lilies at dawn.",
                alt_text="A wooden rowboat moored beneath green willow branches on calm water.",
                static_sample_image="memory-lake.jpg",
                display_order=3,
            )
            GuestbookEntry.objects.create(
                memorial=evelyn,
                author=elena,
                author_display_name="Elena Pendelton",
                relationship_note="Granddaughter",
                flower=GuestbookEntry.FlowerChoice.WILD_ROSE,
                message="I still keep your box of colored pencils on my desk, Grandma. Thinking of you every time the garden roses open.",
                status=GuestbookEntry.ModerationStatus.APPROVED,
            )
            GuestbookEntry.objects.create(
                memorial=evelyn,
                author=clara,
                author_display_name="Clara Pendelton",
                relationship_note="Daughter",
                flower=GuestbookEntry.FlowerChoice.WHITE_LILY,
                message="Leaving a white lily today on your birthday. We shared your apple cake recipe with the whole street.",
                status=GuestbookEntry.ModerationStatus.APPROVED,
            )

        samuel, created_sam = Memorial.objects.get_or_create(
            slug="samuel-mercer-1938",
            defaults={
                "full_name": "Samuel David Mercer",
                "birth_year": 1938,
                "death_year": 2021,
                "biography": (
                    "A retired high-school music teacher and woodworker who repaired violins for students "
                    "who could not afford one. Samuel organized the community orchard and spent decades "
                    "walking the shaded paths of the town arboretum."
                ),
                "portrait_static_asset": "hero-garden.jpg",
                "portrait_alt_text": "Sunlit tree-lined pathway through the botanical arboretum where Samuel walked each morning.",
                "status": Memorial.Status.PUBLISHED,
                "audience": Memorial.Audience.PUBLIC,
                "allow_site_search": True,
                "guestbook_open": True,
                "guestbook_requires_approval": True,
                "is_family_created": True,
                "created_by_label": "Family-created by Clara Pendelton",
                "published_by": clara,
                "published_at": timezone.now(),
            },
        )
        if created_sam:
            PublishedMemory.objects.create(
                memorial=samuel,
                title="The arboretum path at sunrise",
                year_taken="2016",
                story="Samuel walked this tree-lined path almost every morning with a pocket notebook of melody ideas.",
                alt_text="A sunlit paved path winding between lush green trees and foliage.",
                static_sample_image="hero-garden.jpg",
                display_order=1,
            )

        # Consensual accepted relationship between Evelyn and Samuel (lifelong neighbors & orchard co-founders)
        MemorialRelationship.objects.get_or_create(
            from_memorial=evelyn,
            to_memorial=samuel,
            defaults={
                "label_from_to": "Lifelong neighbor & orchard partner of",
                "label_to_from": "Lifelong neighbor & orchard partner of",
                "proposed_by": clara,
                "from_approved": True,
                "to_approved": True,
                "status": MemorialRelationship.Status.ACCEPTED,
            },
        )

        # 4. Curated Local Professional Directory entries for the Oregon pilot region
        providers = [
            {
                "category": DirectoryProvider.Category.FUNERAL_HOME,
                "name": "Willamette Meadow Funeral & Green Burial Care (Sample)",
                "city": "Portland",
                "state": "OR",
                "postal_code": "97205",
                "verified_specialty": "Natural / green burial, cremation, family-led vigils",
                "phone": "(503) 555-0180",
                "website": "https://example.org/willamette-meadow",
                "rating": Decimal("4.9"),
                "review_count": 84,
                "review_source": "Curated pilot listing (placeholder for Google Places)",
                "licensing_lookup_url": "https://www.oregon.gov/omcb/pages/index.aspx",
                "is_paid_placement": False,
            },
            {
                "category": DirectoryProvider.Category.FUNERAL_HOME,
                "name": "Cedar Creek Memorial Chapel (Sample)",
                "city": "Eugene",
                "state": "OR",
                "postal_code": "97401",
                "verified_specialty": "Traditional services, livestream coordination, veterans honors",
                "phone": "(541) 555-0162",
                "website": "https://example.org/cedar-creek",
                "rating": Decimal("4.7"),
                "review_count": 61,
                "review_source": "Curated pilot listing (placeholder for Google Places)",
                "licensing_lookup_url": "https://www.oregon.gov/omcb/pages/index.aspx",
                "is_paid_placement": False,
            },
            {
                "category": DirectoryProvider.Category.ESTATE_LAWYER,
                "name": "Riverbend Elder & Estate Planning Law (Sample)",
                "city": "Portland",
                "state": "OR",
                "postal_code": "97204",
                "verified_specialty": "Wills, revocable living trusts, Oregon healthcare directives",
                "phone": "(503) 555-0128",
                "website": "https://example.org/riverbend-law",
                "rating": Decimal("4.8"),
                "review_count": 53,
                "review_source": "Oregon State Bar verified member (placeholder)",
                "licensing_lookup_url": "https://www.osbar.org/members/membersearch_start.asp",
                "is_paid_placement": False,
            },
            {
                "category": DirectoryProvider.Category.ESTATE_LAWYER,
                "name": "Cascade Family Trusts & Probate Counsel (Sample)",
                "city": "Bend",
                "state": "OR",
                "postal_code": "97701",
                "verified_specialty": "Small-estate administration, guardianship nominations, probate",
                "phone": "(541) 555-0194",
                "website": "https://example.org/cascade-trusts",
                "rating": Decimal("4.6"),
                "review_count": 29,
                "review_source": "Oregon State Bar verified member (placeholder)",
                "licensing_lookup_url": "https://www.osbar.org/members/membersearch_start.asp",
                "is_paid_placement": False,
            },
        ]
        for p in providers:
            DirectoryProvider.objects.get_or_create(name=p["name"], defaults=p)

        self.stdout.write(self.style.SUCCESS("Seeded Virtual Cemetery fictional pilot family & directory data."))
