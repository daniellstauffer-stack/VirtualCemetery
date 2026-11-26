from django.urls import path
from . import views

app_name = "events"

urlpatterns = [
    path("contacts/", views.contacts_view, name="contacts"),
    path("contacts/<uuid:owner_person_id>/", views.contacts_view, name="owner_contacts"),
    path("contacts/<uuid:contact_id>/delete/", views.delete_contact_view, name="delete_contact"),
    path("new/<uuid:owner_person_id>/", views.create_or_edit_event_view, name="create_event"),
    path("<uuid:event_id>/edit/<uuid:owner_person_id>/", views.create_or_edit_event_view, name="edit_event"),
    path("<uuid:event_id>/preview/", views.preview_event_view, name="preview_event"),
    path("<uuid:event_id>/send/", views.send_invitations_view, name="send_invitations"),
    path("opt-out/<str:token>/", views.recipient_opt_out_view, name="opt_out"),
]
