# =============================================================================
# Virtual Cemetery — Google Cloud Infrastructure (Terraform)
# Provisions: Artifact Registry, Cloud SQL (PostgreSQL), Private Media &
# Isolated Evidence Cloud Storage Buckets, Cloud Tasks, Cloud Scheduler,
# Separate Least-Privilege Service Accounts, Secret Manager Placeholders,
# Cloud Run (Web, Private Worker, Migration Job), Workload Identity Federation,
# and Budget Alerts.
# =============================================================================

locals {
  prefix = "vc-${var.environment}"
  required_apis = [
    "run.googleapis.com",
    "sqladmin.googleapis.com",
    "storage.googleapis.com",
    "cloudtasks.googleapis.com",
    "cloudscheduler.googleapis.com",
    "secretmanager.googleapis.com",
    "artifactregistry.googleapis.com",
    "identitytoolkit.googleapis.com",
    "iam.googleapis.com",
    "iamcredentials.googleapis.com",
    "cloudresourcemanager.googleapis.com",
    "logging.googleapis.com",
    "monitoring.googleapis.com",
    "billingbudgets.googleapis.com",
  ]
}

data "google_project" "current" {
  project_id = var.project_id
}

resource "google_project_service" "apis" {
  for_each           = toset(local.required_apis)
  service            = each.value
  disable_on_destroy = false
}

# --- Artifact Registry -------------------------------------------------------
resource "google_artifact_registry_repository" "app" {
  location      = var.region
  repository_id = "virtual-cemetery"
  description   = "Container images for Virtual Cemetery web, worker, and migration jobs"
  format        = "DOCKER"
  depends_on    = [google_project_service.apis]
}

# --- Separate Least-Privilege Service Accounts -------------------------------
resource "google_service_account" "web" {
  account_id   = "${local.prefix}-web"
  display_name = "Virtual Cemetery Web Service (${var.environment})"
  depends_on   = [google_project_service.apis]
}

resource "google_service_account" "worker" {
  account_id   = "${local.prefix}-worker"
  display_name = "Virtual Cemetery Private Worker (${var.environment})"
  depends_on   = [google_project_service.apis]
}

resource "google_service_account" "tasks_invoker" {
  account_id   = "${local.prefix}-tasks-invoker"
  display_name = "Virtual Cemetery Cloud Tasks Invoker (${var.environment})"
  depends_on   = [google_project_service.apis]
}

resource "google_service_account" "github_deployer" {
  account_id   = "${local.prefix}-gh-deploy"
  display_name = "Virtual Cemetery GitHub Actions Deployer (${var.environment})"
  depends_on   = [google_project_service.apis]
}

# --- Cloud SQL for PostgreSQL 16 (with Backups & PITR) -----------------------
resource "google_sql_database_instance" "postgres" {
  name                = "${local.prefix}-pg"
  database_version    = "POSTGRES_16"
  region              = var.region
  deletion_protection = var.environment == "production"

  settings {
    edition           = "ENTERPRISE"
    tier              = var.db_tier
    availability_type = var.db_high_availability ? "REGIONAL" : "ZONAL"

    backup_configuration {
      enabled                        = true
      start_time                     = "03:00"
      point_in_time_recovery_enabled = true
      transaction_log_retention_days = 7
      backup_retention_settings {
        retained_backups = 30
        retention_unit   = "COUNT"
      }
    }

    ip_configuration {
      ipv4_enabled = true
      ssl_mode     = "ENCRYPTED_ONLY"
    }
  }

  depends_on = [google_project_service.apis]
}

resource "google_sql_database" "app_db" {
  name     = "virtualcemetery"
  instance = google_sql_database_instance.postgres.name
}

# --- Private Cloud Storage Buckets (Zero Public Access) ----------------------
resource "google_storage_bucket" "private_media" {
  name                        = "${var.project_id}-${local.prefix}-media"
  location                    = var.region
  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"

  versioning {
    enabled = true
  }

  depends_on = [google_project_service.apis]
}

resource "google_storage_bucket" "case_evidence" {
  name                        = "${var.project_id}-${local.prefix}-evidence"
  location                    = var.region
  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"

  # Automatic scheduled deletion of verification evidence per launch policy
  lifecycle_rule {
    condition {
      age = var.evidence_retention_days
    }
    action {
      type = "Delete"
    }
  }

  depends_on = [google_project_service.apis]
}

# Bucket IAM bindings (narrow access per service identity)
resource "google_storage_bucket_iam_member" "web_media" {
  bucket = google_storage_bucket.private_media.name
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${google_service_account.web.email}"
}

resource "google_storage_bucket_iam_member" "worker_media" {
  bucket = google_storage_bucket.private_media.name
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${google_service_account.worker.email}"
}

resource "google_storage_bucket_iam_member" "web_evidence" {
  bucket = google_storage_bucket.case_evidence.name
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${google_service_account.web.email}"
}

resource "google_storage_bucket_iam_member" "worker_evidence_purge" {
  bucket = google_storage_bucket.case_evidence.name
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${google_service_account.worker.email}"
}

# Cloud SQL client roles for web and worker
resource "google_project_iam_member" "web_sql" {
  project = var.project_id
  role    = "roles/cloudsql.client"
  member  = "serviceAccount:${google_service_account.web.email}"
}

resource "google_project_iam_member" "worker_sql" {
  project = var.project_id
  role    = "roles/cloudsql.client"
  member  = "serviceAccount:${google_service_account.worker.email}"
}

# --- Secret Manager Placeholders (populate versions outside GitHub!) ---------
locals {
  secret_names = [
    "django-secret-key",
    "database-url",
    "worker-shared-secret",
    "postmark-server-token",
    "postmark-webhook-secret",
    "stripe-secret-key",
    "stripe-webhook-secret",
    "facebook-app-secret",
    "google-oauth-client-secret",
    "microsoft-client-secret",
    "google-places-api-key",
    "identity-platform-api-key",
  ]
}

resource "google_secret_manager_secret" "secrets" {
  for_each  = toset(local.secret_names)
  secret_id = "${local.prefix}-${each.value}"
  replication {
    auto {}
  }
  depends_on = [google_project_service.apis]
}

resource "google_secret_manager_secret_iam_member" "web_secrets" {
  for_each  = toset(local.secret_names)
  secret_id = google_secret_manager_secret.secrets[each.value].id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.web.email}"
}

resource "google_secret_manager_secret_iam_member" "worker_secrets" {
  for_each  = toset(["django-secret-key", "database-url", "worker-shared-secret", "postmark-server-token"])
  secret_id = google_secret_manager_secret.secrets[each.value].id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.worker.email}"
}

# --- Rate-Limited Cloud Tasks Queue ------------------------------------------
resource "google_cloud_tasks_queue" "background_jobs" {
  name     = "${local.prefix}-jobs"
  location = var.region

  rate_limits {
    max_dispatches_per_second = 5
    max_concurrent_dispatches = 10
  }

  retry_config {
    max_attempts       = 5
    min_backoff        = "10s"
    max_backoff        = "300s"
    max_doublings      = 4
  }

  depends_on = [google_project_service.apis]
}

resource "google_cloud_tasks_queue_iam_member" "web_enqueuer" {
  location = google_cloud_tasks_queue.background_jobs.location
  name     = google_cloud_tasks_queue.background_jobs.name
  role     = "roles/cloudtasks.enqueuer"
  member   = "serviceAccount:${google_service_account.web.email}"
}

# --- Cloud Run Services (Web + Private Worker + Migration Job) ---------------
resource "google_cloud_run_v2_service" "worker" {
  name     = "${local.prefix}-worker"
  location = var.region
  ingress  = "INGRESS_TRAFFIC_INTERNAL_ONLY"

  template {
    service_account = google_service_account.worker.email
    scaling {
      min_instance_count = 0
      max_instance_count = var.worker_max_instances
    }
    volumes {
      name = "cloudsql"
      cloud_sql_instance {
        instances = [google_sql_database_instance.postgres.connection_name]
      }
    }
    containers {
      image = var.container_image
      volume_mounts {
        name       = "cloudsql"
        mount_path = "/cloudsql"
      }
      env {
        name  = "DJANGO_ENV"
        value = var.environment
      }
      env {
        name  = "DJANGO_DEBUG"
        value = "False"
      }
      env {
        name  = "GCP_PROJECT_ID"
        value = var.project_id
      }
      env {
        name  = "USE_GCS_STORAGE"
        value = "True"
      }
      env {
        name  = "GCP_MEDIA_BUCKET"
        value = google_storage_bucket.private_media.name
      }
      env {
        name  = "GCP_EVIDENCE_BUCKET"
        value = google_storage_bucket.case_evidence.name
      }
      env {
        name  = "CLOUD_TASKS_ENABLED"
        value = "True"
      }
      env {
        name  = "GCP_TASKS_QUEUE_NAME"
        value = google_cloud_tasks_queue.background_jobs.name
      }
      env {
        name  = "SITE_BASE_URL"
        value = var.site_base_url
      }
    }
  }

  lifecycle {
    ignore_changes = [template[0].containers[0].image]
  }

  depends_on = [google_project_service.apis]
}

# ONLY the Cloud Tasks delivery identity may invoke the private worker
resource "google_cloud_run_v2_service_iam_member" "tasks_invoke_worker" {
  project  = var.project_id
  location = google_cloud_run_v2_service.worker.location
  name     = google_cloud_run_v2_service.worker.name
  role     = "roles/run.invoker"
  member   = "serviceAccount:${google_service_account.tasks_invoker.email}"
}

resource "google_cloud_run_v2_service" "web" {
  name     = "${local.prefix}-web"
  location = var.region
  ingress  = "INGRESS_TRAFFIC_ALL"

  template {
    service_account = google_service_account.web.email
    scaling {
      min_instance_count = 0
      max_instance_count = var.web_max_instances
    }
    volumes {
      name = "cloudsql"
      cloud_sql_instance {
        instances = [google_sql_database_instance.postgres.connection_name]
      }
    }
    containers {
      image = var.container_image
      volume_mounts {
        name       = "cloudsql"
        mount_path = "/cloudsql"
      }
      env {
        name  = "DJANGO_ENV"
        value = var.environment
      }
      env {
        name  = "DJANGO_DEBUG"
        value = "False"
      }
      env {
        name  = "LOCAL_AUTH_EMULATOR"
        value = "False"
      }
      env {
        name  = "GCP_PROJECT_ID"
        value = var.project_id
      }
      env {
        name  = "USE_GCS_STORAGE"
        value = "True"
      }
      env {
        name  = "GCP_MEDIA_BUCKET"
        value = google_storage_bucket.private_media.name
      }
      env {
        name  = "GCP_EVIDENCE_BUCKET"
        value = google_storage_bucket.case_evidence.name
      }
      env {
        name  = "CLOUD_TASKS_ENABLED"
        value = "True"
      }
      env {
        name  = "GCP_TASKS_LOCATION"
        value = var.region
      }
      env {
        name  = "GCP_TASKS_QUEUE_NAME"
        value = google_cloud_tasks_queue.background_jobs.name
      }
      env {
        name  = "WORKER_BASE_URL"
        value = google_cloud_run_v2_service.worker.uri
      }
      env {
        name  = "WORKER_OIDC_SERVICE_ACCOUNT"
        value = google_service_account.tasks_invoker.email
      }
      env {
        name  = "SITE_BASE_URL"
        value = var.site_base_url
      }
    }
  }

  lifecycle {
    ignore_changes = [template[0].containers[0].image]
  }

  depends_on = [google_project_service.apis]
}

resource "google_cloud_run_v2_service_iam_member" "web_public" {
  project  = var.project_id
  location = google_cloud_run_v2_service.web.location
  name     = google_cloud_run_v2_service.web.name
  role     = "roles/run.invoker"
  member   = "allUsers"
}

resource "google_cloud_run_v2_job" "migrate" {
  name     = "${local.prefix}-migrate"
  location = var.region

  template {
    template {
      service_account = google_service_account.web.email
      volumes {
        name = "cloudsql"
        cloud_sql_instance {
          instances = [google_sql_database_instance.postgres.connection_name]
        }
      }
      containers {
        image   = var.container_image
        command = ["python", "manage.py", "migrate", "--noinput"]
        volume_mounts {
          name       = "cloudsql"
          mount_path = "/cloudsql"
        }
        env {
          name  = "DJANGO_ENV"
          value = var.environment
        }
      }
    }
  }

  lifecycle {
    ignore_changes = [template[0].template[0].containers[0].image]
  }

  depends_on = [google_project_service.apis]
}

# --- Cloud Scheduler: Nightly Evidence Retention Purge -----------------------
resource "google_cloud_scheduler_job" "purge_evidence" {
  name        = "${local.prefix}-purge-evidence"
  description = "Purge expired death-verification evidence files on schedule"
  schedule    = "0 4 * * *"
  time_zone   = "America/Los_Angeles"
  region      = var.region

  http_target {
    http_method = "POST"
    uri         = "${google_cloud_run_v2_service.worker.uri}/jobs/purge-evidence/"
    oidc_token {
      service_account_email = google_service_account.tasks_invoker.email
      audience              = google_cloud_run_v2_service.worker.uri
    }
  }

  depends_on = [google_project_service.apis]
}

# --- Workload Identity Federation for Keyless GitHub Actions -----------------
resource "google_iam_workload_identity_pool" "github" {
  workload_identity_pool_id = "${local.prefix}-github-pool"
  display_name              = "GitHub Actions Pool (${var.environment})"
  depends_on                = [google_project_service.apis]
}

resource "google_iam_workload_identity_pool_provider" "github" {
  workload_identity_pool_id          = google_iam_workload_identity_pool.github.workload_identity_pool_id
  workload_identity_pool_provider_id = "github-oidc"
  display_name                       = "GitHub OIDC Provider"

  attribute_mapping = {
    "google.subject"       = "assertion.sub"
    "attribute.repository" = "assertion.repository"
    "attribute.ref"        = "assertion.ref"
  }

  attribute_condition = "assertion.repository == '${var.github_repository}'"

  oidc {
    issuer_uri = "https://token.actions.githubusercontent.com"
  }
}

resource "google_service_account_iam_member" "github_wif_binding" {
  service_account_id = google_service_account.github_deployer.name
  role               = "roles/iam.workloadIdentityUser"
  member             = "principalSet://iam.googleapis.com/${google_iam_workload_identity_pool.github.name}/attribute.repository/${var.github_repository}"
}

resource "google_project_iam_member" "github_deployer_roles" {
  for_each = toset([
    "roles/artifactregistry.writer",
    "roles/run.admin",
    "roles/iam.serviceAccountUser",
  ])
  project = var.project_id
  role    = each.value
  member  = "serviceAccount:${google_service_account.github_deployer.email}"
}

# --- Optional Billing Budget Alert (alerts operators; does not cap spend) ----
resource "google_billing_budget" "monthly" {
  count           = var.billing_account_id != "" ? 1 : 0
  billing_account = var.billing_account_id
  display_name    = "Virtual Cemetery ${var.environment} Monthly Budget"

  budget_filter {
    projects = ["projects/${data.google_project.current.number}"]
  }

  amount {
    specified_amount {
      currency_code = "USD"
      units         = tostring(var.monthly_budget_usd)
    }
  }

  threshold_rules {
    threshold_percent = 0.5
  }
  threshold_rules {
    threshold_percent = 0.8
  }
  threshold_rules {
    threshold_percent = 1.0
  }

  depends_on = [google_project_service.apis]
}
