output "web_service_url" {
  value = google_cloud_run_v2_service.web.uri
}

output "worker_service_url" {
  value = google_cloud_run_v2_service.worker.uri
}

output "cloud_sql_connection_name" {
  value = google_sql_database_instance.postgres.connection_name
}

output "private_media_bucket" {
  value = google_storage_bucket.private_media.name
}

output "case_evidence_bucket" {
  value = google_storage_bucket.case_evidence.name
}

output "workload_identity_provider" {
  value = google_iam_workload_identity_pool_provider.github.name
}

output "github_deployer_service_account" {
  value = google_service_account.github_deployer.email
}
