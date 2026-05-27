"""Pull custom field DEFINITIONS for the location.

Custom field VALUES are nested inside each Contact/Opportunity response — we'd
need to re-pull those (with the customFields[] preserved) to populate
fact.ContactCustomFieldValues. This script handles the DEFINITIONS only.

Run:
    .venv/bin/python scripts/pull_custom_fields.py
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
from ghl_api.manifest import Manifest  # noqa: E402
from ghl_api.mappers import CUSTOM_FIELD_COLUMNS, map_custom_field  # noqa: E402

EXPORT_DIR = REPO_ROOT / "data" / "exports"
AUDIT_SCRIPT = REPO_ROOT / "scripts" / "audit_csv.py"


def _now_utc_iso() -> str:
    n = datetime.now(timezone.utc)
    return n.strftime("%Y-%m-%dT%H:%M:%S.") + f"{n.microsecond // 1000:03d}Z"


def main() -> int:
    client = GHLClient.from_env()
    location_id = client.require_location_id()
    extracted_at = _now_utc_iso()

    resp = client.custom_fields.list()
    defs = resp.get("customFields") or []
    print(f"Found {len(defs)} custom field definitions.")

    if not defs:
        print("Nothing to write.")
        return 0

    rows = [map_custom_field(cf, location_id=location_id, extracted_at=extracted_at) for cf in defs]
    path = EXPORT_DIR / "CustomFields_part_001.csv"
    path.write_bytes(b"\xef\xbb\xbf")
    with path.open("a", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(
            f, fieldnames=CUSTOM_FIELD_COLUMNS, lineterminator="\r\n",
            quoting=csv.QUOTE_MINIMAL, extrasaction="ignore",
        )
        w.writeheader()
        for row in rows:
            w.writerow({c: row.get(c, "") for c in CUSTOM_FIELD_COLUMNS})
    print(f"Wrote {len(rows)} rows -> {path.name}")

    rc = subprocess.run(
        [sys.executable, str(AUDIT_SCRIPT), str(path)], check=False
    ).returncode
    if rc != 0:
        print("AUDIT GATE FAILED")
        return rc

    mf = Manifest(
        entity="CustomFields",
        columns=CUSTOM_FIELD_COLUMNS,
        extracted_at_utc=extracted_at,
        shard_size=0,
        output_dir=EXPORT_DIR,
    )
    mf.add_shard(path)
    mf_path = mf.write()
    print(f"Manifest -> {mf_path.name}")
    print(f"Throttle: {client.throttle.stats()}")
    print("OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
