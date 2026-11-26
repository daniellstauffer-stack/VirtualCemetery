variable "project_id" {
  description = "Google Cloud Project ID (use separate projects for staging and production)."
  type        = string
}

variable "region" {
  description = "GCP region matching pilot families and data-residency requirements."
  type        = string
  default     = "us-west1"
}

variable "environment" {
  description = "Deployment environment name (staging or production)."
  type        = string
  validation {
    condition     = contains(["staging", "production"], var.environment)
    error_message = "environment must be either 'staging' or 'production'."
  }
}

variable "github_repository" {
  description = "GitHub repository in owner/repo format for Workload Identity Federation."
  type        = string
  default     = "daniellstauffer-stack/VirtualCemetery"
}

variable "container_image" {
  description = "Full Artifact Registry image URI pinned by @sha256 digest."
  type        = string
  default     = "us-west1-docker.pkg.dev/YOUR_GCP_PROJECT_ID/virtual-cemetery/app:latest"
}

variable "site_base_url" {
  description = "Public HTTPS base URL for this environment."
  type        = string
  default     = "https://staging.example-virtualcemetery.org"
}

variable "db_tier" {
  description = "Cloud SQL PostgreSQL machine tier."
  type        = string
  default     = "db-f1-micro"
}

variable "db_high_availability" {
  description = "Enable regional HA on Cloud SQL when measured outage tolerance justifies cost."
  type        = bool
  default     = false
}

variable "web_max_instances" {
  description = "Max Cloud Run web instances (tuned together with PostgreSQL connection limits)."
  type        = number
  default     = 5
}

variable "worker_max_instances" {
  description = "Max Cloud Run private worker instances."
  type        = number
  default     = 3
}

variable "evidence_retention_days" {
  description = "Days before death-verification evidence files are automatically deleted."
  type        = number
  default     = 90
}

variable "billing_account_id" {
  description = "Optional GCP Billing Account ID placeholder for monthly budget alerts."
  type        = string
  default     = ""
}

variable "monthly_budget_usd" {
  description = "Monthly budget alert threshold in USD (alerts operators; does not cap spend)."
  type        = number
  default     = 100
}
