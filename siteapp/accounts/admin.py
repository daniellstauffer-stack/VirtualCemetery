from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import AccessGrant, AuditEvent, User


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = ("email", "display_name", "person_id", "email_verified", "is_verified_reviewer", "is_deceased_verified")
    search_fields = ("email", "display_name", "person_id")
    ordering = ("email",)
    readonly_fields = ("person_id",)


@admin.register(AccessGrant)
class AccessGrantAdmin(admin.ModelAdmin):
    list_display = ("owner", "recipient_email", "scope", "release_timing", "revoked_at")
    list_filter = ("scope", "release_timing")


@admin.register(AuditEvent)
class AuditEventAdmin(admin.ModelAdmin):
    list_display = ("created_at", "action", "actor", "subject_person_id", "summary")
    list_filter = ("action",)
    readonly_fields = ("created_at", "actor", "subject_person_id", "action", "target_type", "target_id", "summary")
