# Virtual Cemetery — Google Cloud Terraform Infrastructure

This directory defines reproducible Google Cloud environments for **staging** (private rehearsal) and **production**, following [`docs/architecture-and-deployment.md`](../docs/architecture-and-deployment.md).

## Resources Provisioned
- **Cloud Run v2**: Public web service, private worker service (invocable only by Cloud Tasks OIDC identity), and one-shot migration job.
- **Cloud SQL for PostgreSQL 16**: Automated backups (30 retained) and 7-day point-in-time recovery.
- **Two Private Cloud Storage Buckets**: `media` (family uploads/display copies) and `evidence` (narrower access + lifecycle auto-deletion).
- **Cloud Tasks & Cloud Scheduler**: Rate-limited background queue and nightly evidence retention purge.
- **Secret Manager**: Empty secret slots for runtime credentials (populate secret versions via GCP Console or `gcloud secrets versions add` — never commit real secrets to GitHub).
- **Workload Identity Federation**: Keyless authentication from GitHub Actions (`deploy.yml`).
- **Budget Alerts**: Monthly spend notifications (50%, 80%, 100%).

## Usage
```bash
cd infra
cp staging.tfvars.example staging.tfvars
# Edit staging.tfvars with your GCP project ID and billing account ID
terraform init
terraform plan -var-file=staging.tfvars
terraform apply -var-file=staging.tfvars
```
