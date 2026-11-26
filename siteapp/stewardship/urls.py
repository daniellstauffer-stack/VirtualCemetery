from django.urls import path
from . import views

app_name = "stewardship"

urlpatterns = [
    path("", views.manage_stewards_view, name="manage"),
    path("revoke/<uuid:assignment_id>/", views.revoke_steward_view, name="revoke"),
    path("invite/<str:token>/", views.respond_invite_view, name="respond_invite"),
    path("workspace/<uuid:owner_person_id>/", views.steward_workspace_view, name="workspace"),
    path("report/<uuid:owner_person_id>/", views.submit_death_report_view, name="submit_report"),
    path("staff/", views.staff_desk_view, name="staff_desk"),
    path("staff/case/<uuid:report_id>/", views.staff_case_detail_view, name="staff_case"),
    path("staff/case/<uuid:report_id>/evidence/", views.staff_evidence_download_view, name="staff_evidence"),
    path("dispute/", views.dispute_appeal_view, name="dispute"),
]
