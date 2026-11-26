from django.urls import path
from . import views

app_name = "integrations"

urlpatterns = [
    path("facebook/", views.facebook_import_view, name="facebook_import"),
    path("contacts/", views.contact_import_view, name="contact_import"),
    path("directory/", views.directory_view, name="directory"),
    path("support/", views.support_site_view, name="support_site"),
    path("webhooks/stripe/", views.stripe_webhook_view, name="stripe_webhook"),
    path("status/", views.integrations_status_view, name="status"),
]
