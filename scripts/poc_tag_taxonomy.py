"""POC: derive Tag taxonomy from already-pulled Contacts.csv.

Per DATA_RULES.md, Tags are pipe-delimited on the Contacts row. This script:
  1. Reads all Contacts_part_*.csv shards.
  2. Splits Tags column on '|'.
  3. Counts distinct tag occurrences.
  4. Optionally writes a Tags_part_001.csv dim table (one row per tag).

Run:
    .venv/bin/python scripts/poc_tag_taxonomy.py            # just preview
    .venv/bin/python scripts/poc_tag_taxonomy.py --write    # also write CSV
"""
from __future__ import annotations

import argparse
import csv
import subprocess
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from ghl_api.sanitize import clean_text  # noqa: E402
from ghl_api.manifest import Manifest  # noqa: E402

EXPORT_DIR = REPO_ROOT / "data" / "exports"
AUDIT_SCRIPT = REPO_ROOT / "scripts" / "audit_csv.py"

TAG_COLUMNS = [
    "TagId",            # derived: lowercase + slugified
    "TagName",          # display name (preserved case)
    "ContactsCount",
    "FirstSeenAtUtc",
    "LastSeenAtUtc",
    "SourceSystem",
    "SourceSystemId",
    "ExtractedAtUtc",
]


def _slug(tag: str) -> str:
    s = tag.strip().lower()
    return "".join(c if c.isalnum() else "-" for c in s).strip("-")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true",
                    help="Write data/exports/Tags_part_001.csv + manifest + audit")
    ap.add_argument("--top", type=int, default=30, help="Preview top N tags")
    args = ap.parse_args()

    counts: Counter[str] = Counter()
    first_seen: dict[str, str] = {}
    last_seen: dict[str, str] = {}
    case_form: dict[str, str] = {}

    for shard in sorted(EXPORT_DIR.glob("Contacts_part_*.csv")):
        with shard.open(encoding="utf-8-sig", newline="") as f:
            for row in csv.DictReader(f):
                tags_raw = row.get("Tags") or ""
                if not tags_raw:
                    continue
                date_added = row.get("DateAddedUtc") or ""
                for t in tags_raw.split("|"):
                    t = clean_text(t)
                    if not t:
                        continue
                    slug = _slug(t)
                    if not slug:
                        continue
                    counts[slug] += 1
                    case_form.setdefault(slug, t)
                    if date_added:
                        if slug not in first_seen or date_added < first_seen[slug]:
                            first_seen[slug] = date_added
                        if slug not in last_seen or date_added > last_seen[slug]:
                            last_seen[slug] = date_added

    print(f"Distinct tags discovered: {len(counts):,}")
    print(f"Total tag attachments:    {sum(counts.values()):,}")
    print()
    print(f"Top {args.top} tags by contact count:")
    print(f"{'count':>7}  tag")
    for slug, c in counts.most_common(args.top):
        print(f"{c:>7,}  {case_form[slug]}")

    if args.write:
        now = datetime.now(timezone.utc)
        extracted_at = now.strftime("%Y-%m-%dT%H:%M:%S.") + f"{now.microsecond // 1000:03d}Z"
        path = EXPORT_DIR / "Tags_part_001.csv"
        path.write_bytes(b"\xef\xbb\xbf")
        with path.open("a", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=TAG_COLUMNS,
                               lineterminator="\r\n", quoting=csv.QUOTE_MINIMAL,
                               extrasaction="ignore")
            w.writeheader()
            for slug, count in counts.most_common():
                w.writerow({
                    "TagId": slug,
                    "TagName": case_form[slug],
                    "ContactsCount": count,
                    "FirstSeenAtUtc": first_seen.get(slug, ""),
                    "LastSeenAtUtc": last_seen.get(slug, ""),
                    "SourceSystem": "GoHighLevel",
                    "SourceSystemId": slug,
                    "ExtractedAtUtc": extracted_at,
                })
        print(f"\nWrote {len(counts):,} rows -> {path.name}")
        # Audit
        rc = subprocess.run(
            [sys.executable, str(AUDIT_SCRIPT), str(path)], check=False
        ).returncode
        if rc != 0:
            print("AUDIT FAILED")
            return rc
        # Manifest
        mf = Manifest(
            entity="Tags",
            columns=TAG_COLUMNS,
            extracted_at_utc=extracted_at,
            shard_size=0,
            output_dir=EXPORT_DIR,
        )
        mf.add_shard(path)
        mf_path = mf.write()
        print(f"Manifest -> {mf_path.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
