"""Forms for steward invitations, death reports, staff verification actions, and public disputes."""
from __future__ import annotations

from django import forms
from django.conf import settings

from .models import DeathReport, DisputeAppeal, StewardAssignment


class StewardInviteForm(forms.ModelForm):
    class Meta:
        model = StewardAssignment
        fields = ["invitee_name", "invitee_email", "role", "can_organize_funeral"]
        labels = {
            "invitee_name": "Trusted person's name",
            "invitee_email": "Their email address",
            "role": "Steward role",
            "can_organize_funeral": "Also authorize them as Funeral Organizer (to arrange the service and send invitations)",
        }

    def clean_invitee_email(self):
        return self.cleaned_data["invitee_email"].strip().lower()


class DeathReportForm(forms.ModelForm):
    class Meta:
        model = DeathReport
        fields = ["reported_date_of_death", "submitter_relationship", "evidence_summary", "evidence_file"]
        labels = {
            "reported_date_of_death": "Date of death (if known)",
            "submitter_relationship": "Your relationship",
            "evidence_summary": "Supporting evidence details",
            "evidence_file": "Upload supporting document (PDF, JPEG, or PNG — stored privately and auto-deleted on schedule)",
        }
        widgets = {
            "reported_date_of_death": forms.DateInput(attrs={"type": "date"}),
            "evidence_summary": forms.Textarea(attrs={"rows": 4}),
        }

    def clean_evidence_file(self):
        f = self.cleaned_data.get("evidence_file")
        if f:
            if f.size > settings.MAX_UPLOAD_SIZE_BYTES:
                raise forms.ValidationError("Evidence files must be 10 MB or smaller.")
            ct = getattr(f, "content_type", "")
            if ct and ct not in settings.ALLOWED_EVIDENCE_MIME_TYPES:
                raise forms.ValidationError("Please upload a PDF, JPEG, or PNG document.")
        return f


class StaffDecisionForm(forms.Form):
    reason = forms.CharField(
        widget=forms.Textarea(attrs={"rows": 3}),
        label="Recorded reason for this decision",
        help_text="Required. Stored in the staff audit log.",
    )


class DisputeAppealForm(forms.ModelForm):
    class Meta:
        model = DisputeAppeal
        fields = [
            "subject_email_or_name",
            "claimant_name",
            "claimant_email",
            "claimant_phone",
            "claimant_relationship",
            "details",
        ]
        labels = {
            "subject_email_or_name": "Name or email of the account in question",
            "claimant_name": "Your full name",
            "claimant_email": "Your email address",
            "claimant_phone": "Your phone number (optional, speeds up urgent verification)",
            "claimant_relationship": "Your relationship to the account",
            "details": "What happened or what needs to be corrected?",
        }
        widgets = {
            "details": forms.Textarea(attrs={"rows": 4}),
        }
