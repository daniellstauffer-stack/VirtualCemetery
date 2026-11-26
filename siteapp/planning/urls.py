from django.urls import path
from . import views

app_name = "planning"

urlpatterns = [
    path("", views.dashboard_view, name="dashboard"),
    path("edit/", views.edit_plan_view, name="edit_plan"),
    path("memories/add/", views.add_memory_view, name="add_memory"),
    path("memories/<uuid:memory_id>/edit/", views.edit_memory_view, name="edit_memory"),
    path("memories/<uuid:memory_id>/delete/", views.delete_memory_view, name="delete_memory"),
    path("memories/<uuid:memory_id>/image/", views.plan_memory_media_view, name="memory_image"),
    path("shared/<uuid:owner_person_id>/", views.shared_plan_view, name="shared_plan"),
    path("wishes-wizard/", views.wishes_wizard_view, name="wishes_wizard"),
    path("wishes-wizard/download/", views.download_worksheet_view, name="download_worksheet"),
    path("export/", views.export_plan_archive_view, name="export_archive"),
]
