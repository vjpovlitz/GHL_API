"""Per-extract manifest writer.

Records what was produced so a downstream loader (SQL Server BULK INSERT)
can verify shards are present, untruncated, and from the expected schema.

Manifest schema:
    {
      "entity": "Contacts",
      "created_at_utc": "2026-05-23T...",
      "extracted_at_utc": "2026-05-23T...",   # same value across all shards
      "schema_fingerprint": "<sha256 of columns[]>",
      "columns": ["ContactId", ...],
      "row_count_total": 252285,
      "shard_size": 5000,
      "shards": [
        {"file": "Contacts_part_001.csv", "rows": 5000, "bytes": 1234567, "sha256": "..."},
        ...
      ]
    }
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path


def schema_fingerprint(columns: list[str]) -> str:
    """SHA-256 over the column list. Changes if columns add/remove/reorder."""
    blob = "\n".join(columns).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


def file_digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def count_csv_data_rows(path: Path) -> int:
    """Count physical newlines minus one (for the header).

    Safe to use because we sanitize before write — no embedded newlines —
    so physical line count == logical row count. This is the BULK INSERT
    view of the file.
    """
    with path.open("rb") as f:
        n = sum(1 for _ in f)
    return max(0, n - 1)


def now_utc_iso() -> str:
    n = datetime.now(timezone.utc)
    return n.strftime("%Y-%m-%dT%H:%M:%S.") + f"{n.microsecond // 1000:03d}Z"


class Manifest:
    def __init__(
        self,
        *,
        entity: str,
        columns: list[str],
        extracted_at_utc: str,
        shard_size: int,
        output_dir: Path,
    ):
        self.entity = entity
        self.columns = list(columns)
        self.extracted_at_utc = extracted_at_utc
        self.shard_size = shard_size
        self.output_dir = output_dir
        self.shards: list[dict] = []

    def add_shard(self, path: Path) -> dict:
        rows = count_csv_data_rows(path)
        size_bytes = path.stat().st_size
        entry = {
            "file": path.name,
            "rows": rows,
            "bytes": size_bytes,
            "sha256": file_digest(path),
        }
        self.shards.append(entry)
        return entry

    def write(self) -> Path:
        path = self.output_dir / f"{self.entity}.manifest.json"
        payload = {
            "entity": self.entity,
            "created_at_utc": now_utc_iso(),
            "extracted_at_utc": self.extracted_at_utc,
            "schema_fingerprint": schema_fingerprint(self.columns),
            "columns": self.columns,
            "row_count_total": sum(s["rows"] for s in self.shards),
            "shard_size": self.shard_size,
            "shards": self.shards,
        }
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return path
