from django.urls import path
from . import views

app_name = "jobs"

urlpatterns = [
    path("process-photo/", views.process_photo_endpoint, name="process_photo"),
    path("send-invitation/", views.send_invitation_endpoint, name="send_invitation"),
    path("purge-evidence/", views.purge_evidence_endpoint, name="purge_evidence"),
]
