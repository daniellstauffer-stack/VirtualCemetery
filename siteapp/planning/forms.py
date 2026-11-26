"""Forms for My Plan wishes, memories, and the Draft My Wishes wizard."""
from __future__ import annotations

from django import forms
from django.conf import settings

from .models import LifePlan, PlanMemory, WishesWorksheet


class LifePlanForm(forms.ModelForm):
    class Meta:
        model = LifePlan
        fields = [
            "memorial_preferred_name",
            "birth_year",
            "biography_draft",
            "portrait_file",
            "portrait_alt_text",
            "disposition_preference",
            "disposition_notes",
            "service_wishes",
            "emergency_contacts",
            "important_document_locations",
            "memorial_audience_ceiling",
            "allow_site_search",
            "guestbook_requires_approval",
        ]
        labels = {
            "memorial_preferred_name": "Name to display on your memorial",
            "birth_year": "Birth year (optional)",
            "biography_draft": "Your life story in your own words",
            "portrait_file": "Portrait photograph (optional)",
            "portrait_alt_text": "Portrait description for screen readers",
            "disposition_preference": "Burial or cremation preference (private)",
            "disposition_notes": "Private burial or cremation notes",
            "service_wishes": "Funeral or gathering wishes (private)",
            "emergency_contacts": "Emergency contacts to notify first (private)",
            "important_document_locations": "Where important papers are kept (private)",
            "memorial_audience_ceiling": "Maximum audience for your memorial after verified death",
            "allow_site_search": "Allow my published public memorial to be found in site search",
            "guestbook_requires_approval": "Require my steward to approve guestbook notes before visitors see them",
        }
        widgets = {
            "biography_draft": forms.Textarea(attrs={"rows": 5}),
            "disposition_notes": forms.Textarea(attrs={"rows": 3}),
            "service_wishes": forms.Textarea(attrs={"rows": 4}),
            "emergency_contacts": forms.Textarea(attrs={"rows": 3}),
            "important_document_locations": forms.Textarea(attrs={"rows": 3}),
        }

    def clean(self):
        cleaned = super().clean()
        # Prevent site search unless audience ceiling is explicitly Public
        if (
            cleaned.get("allow_site_search")
            and cleaned.get("memorial_audience_ceiling") != LifePlan.MemorialAudienceCeiling.PUBLIC
        ):
            self.add_error(
                "allow_site_search",
                "Site search inclusion is only available if you explicitly choose a Public memorial.",
            )
        portrait = cleaned.get("portrait_file")
        if portrait and hasattr(portrait, "size") and portrait.size > settings.MAX_UPLOAD_SIZE_BYTES:
            self.add_error("portrait_file", "Portrait files must be 10 MB or smaller.")
        return cleaned


class PlanMemoryForm(forms.ModelForm):
    class Meta:
        model = PlanMemory
        fields = [
            "title",
            "year_taken",
            "story",
            "photo_original",
            "alt_text",
            "audience",
            "owner_confirmed_rights",
        ]
        labels = {
            "title": "Memory title",
            "year_taken": "Year or approximate time (optional)",
            "story": "The story behind this photograph",
            "photo_original": "Photograph (JPEG, PNG, or WebP, max 10 MB)",
            "alt_text": "Photo description (for screen readers and captions)",
            "audience": "Who will be able to see this memory?",
            "owner_confirmed_rights": "I took this photograph or have permission to save and share it here.",
        }
        widgets = {
            "story": forms.Textarea(attrs={"rows": 4}),
            "audience": forms.RadioSelect,
        }

    def clean_photo_original(self):
        photo = self.cleaned_data.get("photo_original")
        if photo:
            if photo.size > settings.MAX_UPLOAD_SIZE_BYTES:
                raise forms.ValidationError("Photographs must be 10 MB or smaller.")
            content_type = getattr(photo, "content_type", "")
            if content_type and content_type not in settings.ALLOWED_PHOTO_MIME_TYPES:
                raise forms.ValidationError("Please upload a JPEG, PNG, or WebP photograph.")
        return photo

    def clean_owner_confirmed_rights(self):
        confirmed = self.cleaned_data.get("owner_confirmed_rights")
        if not confirmed:
            raise forms.ValidationError(
                "Please confirm that you own or have permission to include this memory."
            )
        return confirmed


class WishesWorksheetForm(forms.ModelForm):
    class Meta:
        model = WishesWorksheet
        fields = [
            "jurisdiction",
            "dependants_summary",
            "proposed_guardians",
            "asset_categories",
            "intended_gifts",
            "executor_preferences",
            "questions_for_counsel",
        ]
        widgets = {
            "dependants_summary": forms.Textarea(attrs={"rows": 3}),
            "proposed_guardians": forms.Textarea(attrs={"rows": 3}),
            "asset_categories": forms.Textarea(attrs={"rows": 4}),
            "intended_gifts": forms.Textarea(attrs={"rows": 4}),
            "executor_preferences": forms.Textarea(attrs={"rows": 3}),
            "questions_for_counsel": forms.Textarea(attrs={"rows": 4}),
        }
