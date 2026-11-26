from django.apps import AppConfig


class JobsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "siteapp.jobs"
    verbose_name = "Background Worker Jobs"
