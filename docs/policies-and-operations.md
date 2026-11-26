# Pilot Policies & Operating Procedures

Before inviting real families in the pilot jurisdiction (**Oregon, United States**), operators and trained reviewers follow these written commitments (also summarized for families at `/policies/`).

## 1. Death Verification Review Procedure
1. **No automatic triggers.** Account inactivity never files a report, unlocks a plan, or alters a memorial.
2. **Confidential intake.** A death report opens a private staff case. It sends zero family invitations and makes zero changes to any memorial page.
3. **Independent verification.** Assigned reviewers (signed in with staff role + MFA) check independent evidence (e.g., certified record, published obituary with matching details, or direct confirmation from a licensed funeral establishment).
4. **Owner challenge window.** The reviewer contacts the account owner through their verified email (and secondary phone channel if on file) with a direct unauthenticated link to challenge the report (`/stewardship/dispute/`). Silence alone is insufficient without corroborating evidence.
5. **Conflicting claims.** Any competing claim or family dispute pauses the case (`conflict_paused`) and requires independent review by a second trained reviewer.

## 2. Evidence Retention & Privacy
- Case evidence uploads are stored in a dedicated, private Cloud Storage bucket (`vc-<env>-evidence`) separate from family media.
- Only assigned reviewers for a case may download its evidence; every access is logged in `AuditEvent`.
- Guestbook moderation grants zero access to verification evidence.
- Evidence files are automatically purged 90 days after upload (both via GCS object lifecycle rules and the scheduled `/jobs/purge-evidence/` Cloud Scheduler task).

## 3. Appeals & Mistaken-Death Reversal Drill
Any living owner or family member may submit `/stewardship/dispute/` without signing in. Upon confirming an error, a staff reviewer runs the atomic **Reverse approval & restore owner** action:
1. Restores the owner's living status and account access.
2. Immediately suspends/unpublishes the memorial and removes it from site search.
3. Revokes all active private memorial invitation links.
4. Cancels all pending/queued/reconciliation funeral invitation deliveries.
5. Saves an immutable snapshot (`erroneous_notices_snapshot`) of every recipient who had already received a delivered email so staff can promptly send a clear written correction.

## 4. Succession Policy (When No Steward Accepted)
If an owner passes away and no primary or backup steward accepted their invitation, **all unreleased private planning material remains strictly private by default**. Support follows a documented identity-and-next-of-kin check before granting limited authority to create a clearly labeled family memorial without exposing private planning wishes.

## 5. Deletion, Takedown & Backup Recovery
- **Portability:** Account owners may download a readable HTML summary, structured JSON, and owned photos as a ZIP archive at any time (`/plan/export/`).
- **Deletion:** Deleting a memory permanently removes both the original file and EXIF-stripped display copy.
- **Takedowns & Abuse:** Visitors may report abuse or request photo removal via any memorial page or by emailing support.
- **Backups & Recovery Drills:** Cloud SQL retains 30 daily backups and 7 days of point-in-time recovery logs. Before opening the pilot, operators rehearse restoring a backup into an isolated database and reapplying recorded deletion events.

## 6. Service-Closure Commitment
If the operator ever needs to discontinue Virtual Cemetery, families will receive at least **180 days of written notice** via email and prominent site banners, along with full self-service archive exports before systems are decommissioned.
