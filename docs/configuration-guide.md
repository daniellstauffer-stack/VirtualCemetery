# External Accounts & Configuration Guide

Virtual Cemetery runs completely locally out of the box using safe defaults (SQLite/PostgreSQL, local private storage, local auth emulator, console/Mailpit email, and curated pilot directory).

Before launching **staging** or **production**, replace the placeholder values in `.env.example` (and populate Google Cloud Secret Manager versions created by `infra/main.tf`). **Never commit real credentials, service account JSON keys, or real family records to GitHub.**

---

## 1. Google Cloud Platform (GCP)
Create two separate GCP projects: one for **staging** (private rehearsal) and one for **production**.
- `GCP_PROJECT_ID` — Your staging or production GCP Project ID.
- `GCP_REGION` — e.g. `us-west1` (matched to your pilot families and data requirements).
- `DATABASE_URL` — Cloud SQL PostgreSQL 16 connection string stored in Secret Manager (`vc-<env>-database-url`).
- `USE_GCS_STORAGE=True`, `GCP_MEDIA_BUCKET`, `GCP_EVIDENCE_BUCKET` — Private Cloud Storage buckets provisioned by `infra/main.tf` with `public_access_prevention = "enforced"`.
- `CLOUD_TASKS_ENABLED=True`, `GCP_TASKS_QUEUE_NAME`, `WORKER_BASE_URL`, `WORKER_OIDC_SERVICE_ACCOUNT` — Routes photo EXIF stripping and funeral invitation sends through Cloud Tasks to the private Cloud Run worker.

### GitHub Actions Deployment Secrets (Workload Identity Federation)
Configure these in **GitHub Repository Settings → Secrets and variables → Actions** using the outputs from `terraform apply`:
- Repository Variables: `GCP_REGION`, `GCP_STAGING_PROJECT_ID`, `GCP_PROD_PROJECT_ID`
- Repository Secrets: `GCP_STAGING_WIF_PROVIDER`, `GCP_STAGING_DEPLOYER_SA`, `GCP_PROD_WIF_PROVIDER`, `GCP_PROD_DEPLOYER_SA`
- Create a GitHub Environment named `production` with **Required Reviewers** enabled so every production release requires explicit human sign-off.

---

## 2. Google Cloud Identity Platform (Authentication & MFA)
- `LOCAL_AUTH_EMULATOR=False` (in staging and production)
- `GCP_IDENTITY_PLATFORM_PROJECT_ID`
- `GCP_IDENTITY_PLATFORM_API_KEY`
- `GCP_IDENTITY_PLATFORM_AUTH_DOMAIN`
- Enable **Email/Password** with required email verification and **TOTP / SMS Multi-Factor Authentication** for staff reviewers and high-impact owner actions.

---

## 3. Transactional Email (Postmark)
- `EMAIL_PROVIDER=postmark`
- `POSTMARK_SERVER_TOKEN` (stored in Secret Manager)
- `POSTMARK_MESSAGE_STREAM=outbound`
- `EMAIL_FROM_ADDRESS` — Authenticated sending domain (configure DKIM & Return-Path SPF records in Postmark).
- `STAGING_ALLOWED_EMAIL_RECIPIENTS` — In staging, set to a comma-separated allowlist of test addresses/domains (e.g., `@test.example.org`) so staging rehearsals can never email real families.

---

## 4. Facebook / Meta (Optional Login & Future Graph API Import)
- **Works today without Meta App Review:** Living account owners can upload their own downloaded Facebook JSON export via **Import from Facebook archive** (`/integrations/facebook/`). Private messages and other people's posts are automatically excluded.
- **Future gated integration:** Before enabling `FACEBOOK_LOGIN_ENABLED=True`, register an app in Meta for Developers, complete [Meta App Review](https://developers.facebook.com/docs/app-review/), implement data-deletion callbacks, and configure:
  - `FACEBOOK_APP_ID`
  - `FACEBOOK_APP_SECRET` (Secret Manager)
  - `FACEBOOK_REDIRECT_URI`

---

## 5. Funeral Contacts (Google People API & Microsoft Graph)
- **Works today:** Manual entry and guided CSV / vCard (`.vcf`) import with duplicate preview (`/integrations/contacts/`).
- **Future gated integrations:** After completing Google OAuth verification or Microsoft Entra verification (requesting minimum read-only contact scopes and no background sync), configure:
  - Google People: `GOOGLE_PEOPLE_IMPORT_ENABLED=True`, `GOOGLE_OAUTH_CLIENT_ID`, `GOOGLE_OAUTH_CLIENT_SECRET`
  - Microsoft Graph: `MICROSOFT_GRAPH_IMPORT_ENABLED=True`, `MICROSOFT_TENANT_ID`, `MICROSOFT_CLIENT_ID`, `MICROSOFT_CLIENT_SECRET`

---

## 6. Local Professional Directory (Google Places API)
- **Works today:** Curated pilot providers + official state licensing lookup directories (`/integrations/directory/`).
- **Future expansion:** Set `GOOGLE_PLACES_ENABLED=True`, `GOOGLE_PLACES_API_KEY` (Secret Manager), and `GOOGLE_PLACES_DAILY_QUOTA` while adhering to Google Places attribution and storage policies.

---

## 7. Voluntary Site Support (Stripe Hosted Checkout)
- **No bearing on memorial access:** Contributing is strictly optional.
- Configure when ready:
  - `STRIPE_ENABLED=True`
  - `STRIPE_PUBLISHABLE_KEY`
  - `STRIPE_SECRET_KEY` (Secret Manager)
  - `STRIPE_WEBHOOK_SECRET` (Secret Manager) — point Stripe webhook to `https://<your-domain>/integrations/webhooks/stripe/` for `checkout.session.completed` and `checkout.session.async_payment_succeeded`.
  - `STRIPE_PAYEE_LEGAL_NAME` and `STRIPE_TAX_DEDUCTIBLE_STATUS` — verify operator legal entity and tax status before making any deductibility claim.
