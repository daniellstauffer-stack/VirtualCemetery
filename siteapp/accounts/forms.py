"""Forms for account registration, sign-in, step-up MFA, and explicit access grants."""
from __future__ import annotations

from django import forms
from django.contrib.auth import authenticate

from .models import AccessGrant, User


class RegistrationForm(forms.Form):
    display_name = forms.CharField(
        max_length=150,
        label="Your full name",
        help_text="Used inside your private plan and when you leave a signed guestbook note.",
    )
    email = forms.EmailField(label="Email address")
    jurisdiction = forms.CharField(
        max_length=120,
        initial="Oregon, United States",
        label="State or region",
        help_text="Our invitation-only pilot currently supports adults in Oregon, United States.",
    )
    password = forms.CharField(
        widget=forms.PasswordInput,
        min_length=10,
        label="Password",
        help_text="At least 10 characters. Avoid reusing passwords from other sites.",
    )
    password_confirm = forms.CharField(
        widget=forms.PasswordInput,
        label="Confirm password",
    )

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("An account with this email address already exists.")
        return email

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("password") and cleaned.get("password") != cleaned.get("password_confirm"):
            self.add_error("password_confirm", "Passwords do not match.")
        return cleaned


class LoginForm(forms.Form):
    email = forms.EmailField(label="Email address")
    password = forms.CharField(widget=forms.PasswordInput, label="Password")

    def __init__(self, request=None, *args, **kwargs):
        self.request = request
        self.user_cache = None
        super().__init__(*args, **kwargs)

    def clean(self):
        cleaned = super().clean()
        email = (cleaned.get("email") or "").strip().lower()
        password = cleaned.get("password")
        if email and password:
            self.user_cache = authenticate(self.request, username=email, password=password)
            if self.user_cache is None:
                raise forms.ValidationError("Email address or password was not recognized.")
            if not self.user_cache.is_active:
                raise forms.ValidationError(
                    "This account is currently inactive. If you believe this is an error, contact support using our dispute form."
                )
        return cleaned


class StepUpMFAForm(forms.Form):
    code = forms.CharField(
        max_length=12,
        label="6-digit verification code",
        help_text="High-impact actions (replacing a steward or opening the staff verification desk) require a fresh multi-factor check.",
    )


class AccountProfileForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ["display_name", "verified_phone_hint", "jurisdiction", "preferred_text_scale"]
        labels = {
            "display_name": "Your name",
            "verified_phone_hint": "Recovery phone or secondary contact channel",
            "jurisdiction": "Primary jurisdiction",
            "preferred_text_scale": "Preferred text size",
        }
        help_texts = {
            "verified_phone_hint": "Used by a site reviewer to contact you directly if anyone ever submits a death report for your account.",
        }


class AccessGrantForm(forms.ModelForm):
    class Meta:
        model = AccessGrant
        fields = ["recipient_email", "scope", "release_timing", "note_to_recipient"]
        labels = {
            "recipient_email": "Recipient's email address",
            "scope": "What they may read",
            "release_timing": "When they may read it",
            "note_to_recipient": "Short note explaining why you shared this (optional)",
        }

    def clean_recipient_email(self):
        return self.cleaned_data["recipient_email"].strip().lower()
