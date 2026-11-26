from django.contrib import admin
from .models import LifePlan, PlanMemory, WishesWorksheet


@admin.register(LifePlan)
class LifePlanAdmin(admin.ModelAdmin):
    list_display = ("owner", "memorial_preferred_name", "memorial_audience_ceiling", "allow_site_search", "updated_at")


@admin.register(PlanMemory)
class PlanMemoryAdmin(admin.ModelAdmin):
    list_display = ("title", "plan", "audience", "owner_confirmed_rights", "media_status")
    list_filter = ("audience", "media_status")


@admin.register(WishesWorksheet)
class WishesWorksheetAdmin(admin.ModelAdmin):
    list_display = ("owner", "jurisdiction", "updated_at")
