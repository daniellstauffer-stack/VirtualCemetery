# Virtual Cemetery

Virtual Cemetery gives people a private place to plan ahead and gives families a lasting place to remember someone. A person can tell their stories in their own words, choose what others may see, and name someone they trust to care for their memorial.

Imagine your grandfather choosing a photograph and recording the story behind it. He can preview the page with you today. Years later, the person he chose can share that story with the family, and relatives can add memories of their own. His funeral guest list and estate wishes stay in the private part of the service.

## The project blueprint

| Read this | What it helps you decide |
| --- | --- |
| [Product requirements](docs/product-requirements.md) | What families can do, who can see what, how a death is confirmed, and what to build first. |
| [Architecture and deployment](docs/architecture-and-deployment.md) | Which software to build, what to buy from providers, how to organize GitHub, and how to release on Google Cloud. |
| [Policies and operations](docs/policies-and-operations.md) | Pilot verification rules, evidence retention, mistaken-death reversals, succession, deletion, and closure commitments. |
| [Configuration guide](docs/configuration-guide.md) | Step-by-step setup for Google Cloud, Identity Platform, Postmark, Facebook, Google Places, and Stripe placeholders. |
| [Asset attributions](docs/asset-attributions.md) | Licenses and credits for all bundled royalty-free photography. |

## Repository layout

```text
siteapp/                 Django application (family site, restricted staff desk, worker)
  accounts/              Stable person IDs, auth/MFA, access grants, audit history
  planning/              My Plan private workspace, memories, Draft My Wishes wizard, ZIP export
  stewardship/           Steward invites, death reports, staff review desk, appeals/reversals
  memorials/             Separate published snapshot, flowers/guestbook, opt-in relationships, print view
  events/                Private funeral guest list, preview-before-send, idempotent deliveries, opt-out
  integrations/          Postmark email, Facebook archive & CSV/vCard imports, local directory, Stripe support
  jobs/                  Background photo EXIF stripping, invitation delivery worker, evidence purge
  templates/ & static/   WCAG 2.2 AA responsive templates, warm archival CSS, royalty-free imagery
tests/                   Automated release-criteria tests with fictional families
infra/                   Terraform files for Google Cloud staging & production environments
.github/workflows/       CI test workflow & Workload Identity Federation deploy pipeline
```

## Quick local setup

### Option A: Python virtual environment (fastest)
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python manage.py migrate
python manage.py seed_demo_data
python manage.py runserver
```
Open `http://localhost:8000` in your browser.

### Option B: Docker Compose (Django + PostgreSQL 16 + Mailpit local inbox)
```bash
docker compose up --build
```
- Website: `http://localhost:8000`
- Local Mailpit email inbox (inspect funeral invitations & challenge emails): `http://localhost:8025`

### Fictional pilot family accounts (local emulator only)
After running `python manage.py seed_demo_data`, sign in at `/accounts/login/` with:
- **Arthur Pendelton** (Living grandfather / Owner): `arthur@example.org` / `PilotFamily2026!`
- **Clara Pendelton** (Primary Steward & Funeral Organizer): `clara@example.org` / `PilotFamily2026!`
- **Elena Pendelton** (Family Visitor): `elena@example.org` / `PilotFamily2026!`
- **Hannah Brooks** (Staff Site Reviewer): `reviewer@example.org` / `StaffReview2026!`
- Local emulator step-up MFA code: `482910`

## Running the automated release-criteria tests

```bash
pytest -v
```

The test suite in `tests/` verifies all six release criteria from `docs/product-requirements.md`, including strict plan/memorial isolation, immediate steward revocation, false death report dispute & full reversal drills, bilateral relationship visibility, import/delivery/payment idempotency, EXIF metadata stripping, and keyboard/screen-reader accessibility markup.
