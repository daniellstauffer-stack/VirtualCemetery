from django.contrib import admin
from .models import (
    AbuseReport,
    GuestbookEntry,
    Memorial,
    MemorialInvite,
    MemorialRelationship,
    PublishedMemory,
)


@admin.register(Memorial)
class MemorialAdmin(admin.ModelAdmin):
    list_display = ("full_name", "slug", "status", "audience", "allow_site_search", "published_at")
    list_filter = ("status", "audience", "allow_site_search")


@admin.register(PublishedMemory)
class PublishedMemoryAdmin(admin.ModelAdmin):
    list_display = ("title", "memorial", "year_taken", "display_order")


@admin.register(MemorialInvite)
class MemorialInviteAdmin(admin.ModelAdmin):
    list_display = ("memorial", "intended_email", "expires_at", "redeemed_at", "revoked_at")


@admin.register(GuestbookEntry)
class GuestbookEntryAdmin(admin.ModelAdmin):
    list_display = ("memorial", "author_display_name", "flower", "status", "created_at")
    list_filter = ("status", "flower")


@admin.register(MemorialRelationship)
class MemorialRelationshipAdmin(admin.ModelAdmin):
    list_display = ("from_memorial", "label_from_to", "to_memorial", "status")


@admin.register(AbuseReport)
class AbuseReportAdmin(admin.ModelAdmin):
    list_display = ("memorial", "status", "created_at")
