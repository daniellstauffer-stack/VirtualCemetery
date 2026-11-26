"""Forms for managing private funeral contacts and funeral event invitations."""
from __future__ import annotations

from django import forms
from .models import FuneralContact, FuneralEvent


class FuneralContactForm(forms.ModelForm):
    class Meta:
        model = FuneralContact
        fields = ["full_name", "email", "relationship"]
        labels = {
            "full_name": "Recipient's full name",
            "email": "Email address",
            "relationship": "Relationship (optional)",
        }

    def clean_email(self):
        return self.cleaned_data["email"].strip().lower()


class FuneralEventForm(forms.ModelForm):
    class Meta:
        model = FuneralEvent
        fields = [
            "title",
            "event_datetime",
            "time_zone",
            "location_name",
            "location_address",
            "livestream_url",
            "invitation_wording",
        ]
        labels = {
            "title": "Gathering or service title",
            "event_datetime": "Date and time",
            "time_zone": "Time zone (e.g., America/Los_Angeles)",
            "location_name": "Venue name (kept within event audience)",
            "location_address": "Venue address (kept within event audience)",
            "livestream_url": "Private livestream link (optional, kept within event audience)",
            "invitation_wording": "Invitation message",
        }
        widgets = {
            "event_datetime": forms.DateTimeInput(attrs={"type": "datetime-local"}),
            "location_address": forms.Textarea(attrs={"rows": 2}),
            "invitation_wording": forms.Textarea(attrs={"rows": 4}),
        }
