from django.contrib import admin
from .models import DirectoryProvider, SiteContribution


@admin.register(SiteContribution)
class SiteContributionAdmin(admin.ModelAdmin):
    list_display = ("stripe_session_id", "amount_display", "status", "contributor_email", "created_at")
    list_filter = ("status", "currency")


@admin.register(DirectoryProvider)
class DirectoryProviderAdmin(admin.ModelAdmin):
    list_display = ("name", "category", "city", "state", "postal_code", "rating", "is_paid_placement")
    list_filter = ("category", "state", "is_paid_placement")
