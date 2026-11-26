from django.urls import path
from . import views

app_name = "memorials"

urlpatterns = [
    path("discover/", views.discover_view, name="discover"),
    path("preview/", views.owner_preview_view, name="owner_preview"),
    path("family-create/", views.family_create_memorial_view, name="family_create"),
    path("prepare-release/<uuid:owner_person_id>/", views.prepare_release_view, name="prepare_release"),
    path("invite/<str:token>/", views.redeem_memorial_invite_view, name="redeem_invite"),
    path("<slug:slug>/", views.memorial_detail_view, name="detail"),
    path("<slug:slug>/print/", views.memorial_print_view, name="print"),
    path("<slug:slug>/portrait/", views.published_portrait_image_view, name="portrait_image"),
    path("<slug:slug>/memory/<uuid:memory_id>/image/", views.published_memory_image_view, name="memory_image"),
    path("<slug:slug>/guestbook/add/", views.add_guestbook_entry_view, name="add_guestbook"),
    path("<slug:slug>/guestbook/<uuid:entry_id>/moderate/", views.moderate_guestbook_view, name="moderate_guestbook"),
    path("<slug:slug>/guestbook/toggle/", views.toggle_guestbook_view, name="toggle_guestbook"),
    path("<slug:slug>/audience/", views.change_memorial_audience_view, name="change_audience"),
    path("<slug:slug>/invite/create/", views.create_memorial_invite_view, name="create_invite"),
    path("<slug:slug>/relationships/propose/", views.propose_relationship_view, name="propose_relationship"),
    path("<slug:slug>/relationships/<uuid:relationship_id>/respond/", views.respond_relationship_view, name="respond_relationship"),
    path("<slug:slug>/report/", views.report_abuse_view, name="report_abuse"),
]
