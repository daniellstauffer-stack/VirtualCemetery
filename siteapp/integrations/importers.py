"""Guided user-controlled importers for Facebook JSON exports and CSV/vCard contact files.

Follows the architecture blueprint:
- Facebook archive import previews locally, excludes messages and other people's posts,
  detects duplicates, requires rights confirmation, saves only selected items, and never
  retains temporary archives.
- Contact CSV/vCard import previews rows, detects duplicates against existing private
  contacts, and lets the user cancel before anything is saved.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
from datetime import datetime, timezone


def parse_facebook_export_json(raw_bytes: bytes, existing_external_ids: set[str]) -> list[dict]:
    """Parse a user-downloaded Facebook JSON archive (e.g. your_posts_1.json).

    Explicitly excludes private messages (`messages` / `participants`) and items
    authored by someone else (`other_author` / `is_other_person_post`).
    """
    data = json.loads(raw_bytes.decode("utf-8"))

    # Refuse private message archives
    if isinstance(data, dict) and ("messages" in data or "participants" in data):
        raise ValueError(
            "Private Facebook message threads are excluded by policy. Please upload only your own posts or photo stories export."
        )

    items = data if isinstance(data, list) else data.get("posts", data.get("status_updates", []))
    if not isinstance(items, list):
        raise ValueError("Unrecognized Facebook JSON export structure.")

    candidates = []
    for idx, entry in enumerate(items[:100]):
        if not isinstance(entry, dict):
            continue
        # Exclude posts explicitly flagged as belonging to another person
        if entry.get("is_other_person_post") or entry.get("authored_by_other"):
            continue

        ts = entry.get("timestamp")
        year_str = ""
        if isinstance(ts, (int, float)) and ts > 0:
            year_str = str(datetime.fromtimestamp(ts, tz=timezone.utc).year)
        elif entry.get("year"):
            year_str = str(entry["year"])

        text = ""
        if isinstance(entry.get("data"), list):
            for block in entry["data"]:
                if isinstance(block, dict) and block.get("post"):
                    text = block["post"]
                    break
        if not text:
            text = entry.get("story") or entry.get("description") or entry.get("post") or ""

        title = entry.get("title") or (text[:70] + ("..." if len(text) > 70 else "")) or f"Facebook Memory #{idx + 1}"
        if not text.strip() and not entry.get("title"):
            continue

        ext_id = str(
            entry.get("id")
            or hashlib.sha256(f"{ts}:{title}:{text[:80]}".encode("utf-8")).hexdigest()[:24]
        )
        candidates.append(
            {
                "external_id": f"fb:{ext_id}",
                "title": title[:180],
                "year_taken": year_str,
                "story": text.strip(),
                "is_duplicate": f"fb:{ext_id}" in existing_external_ids,
            }
        )
    return candidates


def parse_contacts_csv_or_vcard(raw_text: str, filename: str, existing_emails: set[str]) -> list[dict]:
    """Parse CSV or vCard (.vcf) contact records, flagging duplicates without saving yet."""
    lower_name = (filename or "").lower()
    parsed = []
    seen_in_file: set[str] = set()

    if lower_name.endswith(".vcf") or "BEGIN:VCARD" in raw_text.upper():
        current_name = ""
        current_email = ""
        current_rel = ""
        for line in raw_text.splitlines():
            line = line.strip()
            upper = line.upper()
            if upper == "BEGIN:VCARD":
                current_name = current_email = current_rel = ""
            elif upper.startswith("FN:"):
                current_name = line[3:].strip()
            elif "EMAIL" in upper and ":" in line:
                current_email = line.split(":", 1)[1].strip().lower()
            elif upper.startswith("NOTE:"):
                current_rel = line[5:].strip()[:100]
            elif upper == "END:VCARD":
                if current_email:
                    is_dup = current_email in existing_emails or current_email in seen_in_file
                    seen_in_file.add(current_email)
                    parsed.append(
                        {
                            "full_name": current_name or current_email.split("@")[0],
                            "email": current_email,
                            "relationship": current_rel,
                            "is_duplicate": is_dup,
                        }
                    )
    else:
        reader = csv.DictReader(io.StringIO(raw_text))
        for row in reader:
            norm = {k.strip().lower(): (v or "").strip() for k, v in row.items() if k}
            email = (norm.get("email") or norm.get("e-mail") or norm.get("email address") or "").lower()
            if not email or "@" not in email:
                continue
            name = (
                norm.get("name")
                or norm.get("full_name")
                or norm.get("full name")
                or f"{norm.get('first name', '')} {norm.get('last name', '')}".strip()
                or email.split("@")[0]
            )
            rel = norm.get("relationship") or norm.get("notes") or ""
            is_dup = email in existing_emails or email in seen_in_file
            seen_in_file.add(email)
            parsed.append(
                {
                    "full_name": name[:150],
                    "email": email,
                    "relationship": rel[:100],
                    "is_duplicate": is_dup,
                }
            )
    return parsed
