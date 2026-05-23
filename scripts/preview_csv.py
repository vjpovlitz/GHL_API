"""Preview CSVs with PII redaction (Rule 7).

Masks Email/Phone/Body fields after the first 4 chars before printing.
"""
from __future__ import annotations

import csv
from pathlib import Path

EXPORT_DIR = Path(__file__).resolve().parent.parent / "data" / "exports"
MASKED_FIELDS = {"Email", "Phone", "ContactEmail", "ContactPhone", "Body", "LastMessageBody", "Address1"}


def mask(v: str) -> str:
    if not v or len(v) <= 4:
        return v or ""
    return v[:4] + "*" * min(len(v) - 4, 12)


def preview(filename: str, n: int = 3) -> None:
    path = EXPORT_DIR / filename
    print(f"\n{'=' * 78}")
    print(f"FILE: {filename}   ({path.stat().st_size:,} bytes)")
    print("=" * 78)
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        cols = reader.fieldnames or []
        print(f"\nCOLUMNS ({len(cols)}):")
        for c in cols:
            print(f"  - {c}")
        print(f"\nSAMPLE ROWS (first {n}, PII masked):")
        for i, row in enumerate(reader):
            if i >= n:
                break
            print(f"\n  [row {i + 1}]")
            for k, v in row.items():
                if k in MASKED_FIELDS:
                    v = mask(v)
                if len(v) > 80:
                    v = v[:80] + "..."
                print(f"    {k:24} = {v!r}")


def main() -> None:
    for fn in ["Contacts.csv", "Conversations.csv", "ConversationMessages.csv"]:
        preview(fn)


if __name__ == "__main__":
    main()
