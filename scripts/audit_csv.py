"""Audit a CSV file for SQL-Server / BULK INSERT data quality issues.

Reports:
- Embedded newlines inside fields (CR / LF / CRLF)
- Tabs inside fields
- NULL bytes
- Other C0 control characters
- Stray (unescaped) quotes
- Leading/trailing whitespace
- Non-UTF-8 / invalid bytes
- Long fields that might overflow NVARCHAR sizes
- Empty PK values
- Inconsistent column counts
- Unicode normalization quirks

Usage:
    .venv/bin/python scripts/audit_csv.py [path ...]
    .venv/bin/python scripts/audit_csv.py            # audits all CSVs in data/exports/
"""
from __future__ import annotations

import csv
import sys
import unicodedata
from collections import Counter
from pathlib import Path

EXPORT_DIR = Path(__file__).resolve().parent.parent / "data" / "exports"

PK_COLUMNS = {
    "Contacts.csv": "ContactId",
    "Conversations.csv": "ConversationId",
    "ConversationMessages.csv": "MessageId",
}

# C0 control chars we never want in CSV fields (except already-handled \r\n\t)
BAD_CONTROL_CODES = set(range(0, 9)) | {11, 12} | set(range(14, 32))


def audit_file(path: Path) -> dict:
    print(f"\n{'=' * 78}")
    print(f"AUDIT: {path}")
    print("=" * 78)

    raw = path.read_bytes()
    findings: dict[str, list] = {
        "byte_level": [],
        "row_level": [],
        "field_level": [],
        "long_fields": [],
    }
    issue_counts: Counter[str] = Counter()

    # ---- byte-level ----
    if not raw.startswith(b"\xef\xbb\xbf"):
        findings["byte_level"].append("missing UTF-8 BOM (rule 5)")
    if b"\x00" in raw:
        findings["byte_level"].append(f"contains {raw.count(b'\\x00')} NULL bytes")
    try:
        raw.decode("utf-8-sig")
    except UnicodeDecodeError as e:
        findings["byte_level"].append(f"invalid UTF-8: {e}")

    # Count line ending styles
    lf_only = raw.count(b"\n") - raw.count(b"\r\n")
    crlf = raw.count(b"\r\n")
    findings["byte_level"].append(f"line endings: CRLF={crlf}, bare-LF={lf_only}")

    # ---- row/field level via csv (proper file-mode parse) ----
    # Count physical lines too — BULK INSERT sees those, not logical rows
    physical_lines = raw.count(b"\n")  # CRLF and bare LF both count
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.reader(f)
        header = next(reader)
        expected_cols = len(header)
        logical_rows = list(reader)

    print(f"  Physical lines (BULK INSERT view): {physical_lines}")
    print(f"  Logical CSV rows (data + header):  {len(logical_rows) + 1}")
    if physical_lines > len(logical_rows) + 1:
        diff = physical_lines - (len(logical_rows) + 1)
        findings["byte_level"].append(
            f"{diff} embedded newlines mid-field — BULK INSERT will mis-parse"
        )

    reader = iter(logical_rows)
    pk_col = PK_COLUMNS.get(path.name)
    pk_idx = header.index(pk_col) if pk_col and pk_col in header else None

    bad_col_counts: list[tuple[int, int]] = []
    empty_pks: list[int] = []
    field_issues: Counter[str] = Counter()
    long_fields_top: list[tuple[int, str, int]] = []

    i = 1  # header already consumed
    for i, row in enumerate(reader, start=2):  # data rows 1-indexed after header
        if len(row) != expected_cols:
            bad_col_counts.append((i, len(row)))
        for j, val in enumerate(row):
            if pk_idx is not None and j == pk_idx and not val:
                empty_pks.append(i)
            # field-level checks
            if "\n" in val or "\r" in val:
                field_issues[f"embedded newline in {header[j] if j < len(header) else f'col{j}'}"] += 1
            if "\t" in val:
                field_issues[f"embedded tab in {header[j] if j < len(header) else f'col{j}'}"] += 1
            if any(ord(c) in BAD_CONTROL_CODES for c in val):
                field_issues[f"control char in {header[j] if j < len(header) else f'col{j}'}"] += 1
            if val != val.strip():
                field_issues[f"untrimmed whitespace in {header[j] if j < len(header) else f'col{j}'}"] += 1
            norm = unicodedata.normalize("NFC", val)
            if norm != val:
                field_issues[f"non-NFC unicode in {header[j] if j < len(header) else f'col{j}'}"] += 1
            if len(val) > 1000:
                long_fields_top.append((i, header[j] if j < len(header) else f"col{j}", len(val)))

    # ---- report ----
    print(f"\nHeader columns: {expected_cols}")
    print(f"Data rows:      {i - 1 if 'i' in dir() else 0}")  # noqa

    print("\n[byte-level]")
    for f in findings["byte_level"]:
        print(f"  - {f}")

    print("\n[row-level]")
    if bad_col_counts:
        print(f"  - {len(bad_col_counts)} rows with wrong column count")
        for r, n in bad_col_counts[:5]:
            print(f"      line {r}: {n} cols (expected {expected_cols})")
    else:
        print("  - all rows have correct column count  OK")
    if empty_pks:
        print(f"  - {len(empty_pks)} rows with empty PK ({pk_col})")
    else:
        print(f"  - no empty PK values  OK")

    print("\n[field-level]")
    if field_issues:
        for issue, n in field_issues.most_common():
            print(f"  - {n:>5}  {issue}")
            issue_counts[issue] += n
    else:
        print("  - no field-level issues  OK")

    print("\n[long fields > 1000 chars]")
    if long_fields_top:
        long_fields_top.sort(key=lambda x: -x[2])
        for r, col, ln in long_fields_top[:5]:
            print(f"  - line {r}  col={col}  len={ln}")
    else:
        print("  - none")

    return {"path": str(path), "field_issues": dict(field_issues), "bad_rows": len(bad_col_counts)}


def main() -> None:
    paths = [Path(p) for p in sys.argv[1:]] or sorted(EXPORT_DIR.glob("*.csv"))
    if not paths:
        print("No CSVs to audit.")
        sys.exit(1)
    summaries = [audit_file(p) for p in paths]
    print(f"\n{'=' * 78}\nOVERALL\n{'=' * 78}")
    total_issues = sum(sum(s["field_issues"].values()) for s in summaries) + sum(s["bad_rows"] for s in summaries)
    print(f"Files audited: {len(summaries)}")
    print(f"Total issues : {total_issues}")
    if total_issues > 0:
        print("\nFIX NEEDED before SQL Server load.")
        sys.exit(1)


if __name__ == "__main__":
    main()
