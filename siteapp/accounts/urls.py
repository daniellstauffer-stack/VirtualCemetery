from django.urls import path
from . import views

app_name = "accounts"

urlpatterns = [
    path("register/", views.register_view, name="register"),
    path("login/", views.login_view, name="login"),
    path("logout/", views.logout_view, name="logout"),
    path("mfa/", views.step_up_mfa_view, name="mfa"),
    path("profile/", views.profile_view, name="profile"),
    path("verify-email/", views.verify_email_view, name="verify_email"),
    path("grants/", views.access_grants_view, name="grants"),
    path("grants/<uuid:grant_id>/revoke/", views.revoke_grant_view, name="revoke_grant"),
    path("text-scale/", views.set_text_scale_view, name="text_scale"),
]
