"""Forms for guestbook tributes, private memorial invites, relationships, and abuse reports."""
from __future__ import annotations

from django import forms
from .models import AbuseReport, GuestbookEntry, Memorial, MemorialInvite


class GuestbookEntryForm(forms.ModelForm):
    class Meta:
        model = GuestbookEntry
        fields = ["flower", "relationship_note", "message"]
        labels = {
            "flower": "Leave a free virtual flower",
            "relationship_note": "How you knew them (optional)",
            "message": "Share a memory or note of remembrance",
        }
        widgets = {
            "message": forms.Textarea(attrs={"rows": 3, "placeholder": "Write a quiet note or favorite memory..."}),
        }

    def clean(self):
        cleaned = super().clean()
        if not cleaned.get("flower") and not (cleaned.get("message") or "").strip():
            raise forms.ValidationError("Please choose a virtual flower or write a short note.")
        return cleaned


class MemorialInviteForm(forms.ModelForm):
    class Meta:
        model = MemorialInvite
        fields = ["intended_name", "intended_email"]
        labels = {
            "intended_name": "Invited family member or friend's name",
            "intended_email": "Their email address",
        }

    def clean_intended_email(self):
        return self.cleaned_data["intended_email"].strip().lower()


class AbuseReportForm(forms.ModelForm):
    class Meta:
        model = AbuseReport
        fields = ["reason"]
        labels = {"reason": "Tell us what is harmful or inaccurate so a steward or reviewer can act"}
        widgets = {"reason": forms.Textarea(attrs={"rows": 3})}


class RelationshipProposalForm(forms.Form):
    target_slug = forms.SlugField(label="Address slug of the other memorial")
    label_from_to = forms.CharField(
        max_length=100,
        label="How this person relates to them (e.g., Husband of, Mother of, Lifelong friend of)",
    )
    label_to_from = forms.CharField(
        max_length=100,
        label="How they relate back (e.g., Wife of, Daughter of, Lifelong friend of)",
    )


class FamilyCreatedMemorialForm(forms.ModelForm):
    authority_statement = forms.CharField(
        widget=forms.Textarea(attrs={"rows": 3}),
        label="Your relationship and authority to create this memorial",
        help_text="Family-created pages are for loved ones who did not have a Virtual Cemetery account. They grant no access to any private account or social profile.",
    )

    class Meta:
        model = Memorial
        fields = ["full_name", "birth_year", "death_year", "biography", "audience"]
        labels = {
            "full_name": "Loved one's full name",
            "birth_year": "Birth year",
            "death_year": "Year of passing",
            "biography": "Life story",
            "audience": "Who may view this memorial",
        }
        widgets = {"biography": forms.Textarea(attrs={"rows": 5})}
