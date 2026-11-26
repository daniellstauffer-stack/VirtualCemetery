from django.contrib import admin
from .models import FuneralContact, FuneralEvent, InvitationDelivery


@admin.register(FuneralContact)
class FuneralContactAdmin(admin.ModelAdmin):
    list_display = ("full_name", "email", "owner", "opted_out", "source")


@admin.register(FuneralEvent)
class FuneralEventAdmin(admin.ModelAdmin):
    list_display = ("title", "owner", "version", "status", "event_datetime")


@admin.register(InvitationDelivery)
class InvitationDeliveryAdmin(admin.ModelAdmin):
    list_display = ("recipient_email", "event", "event_version", "status", "sent_at")
    list_filter = ("status",)
