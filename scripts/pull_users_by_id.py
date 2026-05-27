"""Derive ghl.Users by enumerating distinct user IDs from existing data + GET /users/{id}.

The /users/search endpoint needs companyId we don't have under PIT. But
GET /users/{id} works fine. This script:
  1. Collects all distinct UserIds referenced anywhere (Contacts.AssignedToUserId,
     Opportunities.AssignedToUserId).
  2. Calls GET /users/{id} for each.
  3. Writes Users_part_001.csv via map_user().
  4. Audits + manifests.

Run:
    .venv/bin/python scripts/pull_users_by_id.py
"""
from __future__ import annotations

import csv
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from ghl_api import GHLClient  # noqa: E402
from ghl_api.exceptions import GHLAPIError  # noqa: E402
from ghl_api.manifest import Manifest  # noqa: E402
from ghl_api.mappers import USER_COLUMNS, map_user  # noqa: E402

EXPORT_DIR = REPO_ROOT / "data" / "exports"
AUDIT_SCRIPT = REPO_ROOT / "scripts" / "audit_csv.py"


def _now_utc_iso() -> str:
    n = datetime.now(timezone.utc)
    return n.strftime("%Y-%m-%dT%H:%M:%S.") + f"{n.microsecond // 1000:03d}Z"


def collect_user_ids() -> set[str]:
    ids: set[str] = set()
    # Contacts
    for shard in sorted(EXPORT_DIR.glob("Contacts_part_*.csv")):
        with shard.open(encoding="utf-8-sig", newline="") as f:
            for r in csv.DictReader(f):
                u = (r.get("AssignedToUserId") or "").strip()
                if u:
                    ids.add(u)
    # Opportunities
    for shard in sorted(EXPORT_DIR.glob("Opportunities_part_*.csv")):
        with shard.open(encoding="utf-8-sig", newline="") as f:
            for r in csv.DictReader(f):
                u = (r.get("AssignedToUserId") or "").strip()
                if u:
                    ids.add(u)
    return ids


def main() -> int:
    ids = collect_user_ids()
    print(f"Distinct user IDs found across Contacts+Opportunities: {len(ids):,}")
    if not ids:
        print("Nothing to do.")
        return 0

    client = GHLClient.from_env()
    extracted_at = _now_utc_iso()
    users_raw: list[dict] = []
    failed: list[tuple[str, str]] = []

    for i, uid in enumerate(sorted(ids), start=1):
        try:
            resp = client.users.get(uid)
            users_raw.append(resp)
            if i % 10 == 0:
                print(f"  fetched {i}/{len(ids)}  (burst_rem={client.throttle.burst_remaining})")
        except GHLAPIError as e:
            failed.append((uid, f"{e.status_code}: {e}"))

    print(f"\nFetched {len(users_raw)} users; failed {len(failed)}.")
    for uid, msg in failed[:5]:
        print(f"  FAIL {uid}: {msg}")

    if not users_raw:
        print("No users fetched — abort.")
        return 1

    rows = [map_user(u, extracted_at=extracted_at) for u in users_raw]
    path = EXPORT_DIR / "Users_part_001.csv"
    path.write_bytes(b"\xef\xbb\xbf")
    with path.open("a", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(
            f, fieldnames=USER_COLUMNS, lineterminator="\r\n",
            quoting=csv.QUOTE_MINIMAL, extrasaction="ignore",
        )
        w.writeheader()
        for row in rows:
            w.writerow({c: row.get(c, "") for c in USER_COLUMNS})
    print(f"Wrote {len(rows)} rows -> {path.name}")

    # Audit
    rc = subprocess.run(
        [sys.executable, str(AUDIT_SCRIPT), str(path)], check=False
    ).returncode
    if rc != 0:
        print("AUDIT GATE FAILED")
        return rc

    # Manifest
    mf = Manifest(
        entity="Users",
        columns=USER_COLUMNS,
        extracted_at_utc=extracted_at,
        shard_size=0,
        output_dir=EXPORT_DIR,
    )
    mf.add_shard(path)
    mf_path = mf.write()
    print(f"Manifest -> {mf_path.name}")

    print(f"\nThrottle: {client.throttle.stats()}")
    print("OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
