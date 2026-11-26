"""Root URL configuration for Virtual Cemetery."""
from django.contrib import admin
from django.urls import include, path

from siteapp.memorials import views as memorial_views

urlpatterns = [
    path("", memorial_views.home_view, name="home"),
    path("healthz/", memorial_views.health_check_view, name="healthz"),
    path("policies/", memorial_views.policies_view, name="policies"),
    path("accounts/", include("siteapp.accounts.urls")),
    path("plan/", include("siteapp.planning.urls")),
    path("stewardship/", include("siteapp.stewardship.urls")),
    path("memorials/", include("siteapp.memorials.urls")),
    path("events/", include("siteapp.events.urls")),
    path("integrations/", include("siteapp.integrations.urls")),
    path("jobs/", include("siteapp.jobs.urls")),
    path("django-admin/", admin.site.urls),
]
