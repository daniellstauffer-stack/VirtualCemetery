from django.contrib import admin
from .models import DeathReport, DisputeAppeal, StewardAssignment, VerificationDecision


@admin.register(StewardAssignment)
class StewardAssignmentAdmin(admin.ModelAdmin):
    list_display = ("owner", "invitee_name", "invitee_email", "role", "status", "can_organize_funeral", "expires_at")
    list_filter = ("role", "status")


@admin.register(DeathReport)
class DeathReportAdmin(admin.ModelAdmin):
    list_display = ("id", "subject_owner", "status", "assigned_reviewer", "independent_evidence_checked", "created_at")
    list_filter = ("status",)


@admin.register(VerificationDecision)
class VerificationDecisionAdmin(admin.ModelAdmin):
    list_display = ("report", "action", "reviewer", "created_at")


@admin.register(DisputeAppeal)
class DisputeAppealAdmin(admin.ModelAdmin):
    list_display = ("subject_email_or_name", "claimant_name", "claimant_relationship", "status", "created_at")
