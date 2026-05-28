"""Daily incremental refresh orchestrator.

Strategy:
  1. Read each entity's latest manifest -> ExtractedAtUtc (or default to N days ago).
  2. For each entity that supports incremental:
     - Pull records updated since that timestamp
     - Write to entity_inc_<ts>_part_*.csv
     - Audit
  3. Upsert each new inc shard via MERGE into SQL Server.
  4. Refresh ContactTags + smoke-test views.

Entities & their incremental strategy:
  conversations  — --since-iso (filter lastMessageDate)
  opportunities  — --since-iso (filter updatedAt, client-side)
  messages       — --since-days N (existing driver-based pull)

Skipped (low churn):
  contacts, pipelines, users, tags, customfields, appointments

Usage:
  .venv/bin/python scripts/refresh_daily.py [--lookback-days N] [--dry-run]
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import traceback
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))
sys.path.insert(0, str(REPO_ROOT / "scripts"))

try:
    from dotenv import load_dotenv
    load_dotenv(REPO_ROOT / ".env")
except ImportError:
    pass

from ghl_api.alerts import send_alert  # noqa: E402
from load_to_sql import connect  # noqa: E402

EXPORT_DIR = REPO_ROOT / "data" / "exports"
PYTHON = sys.executable
RUN_BATCH = REPO_ROOT / "scripts" / "run_batch.py"
LOAD_SQL = REPO_ROOT / "scripts" / "load_to_sql.py"
SMOKE_VIEWS = REPO_ROOT / "scripts" / "smoke_views.py"


class RefreshError(Exception):
    """A refresh step exited non-zero; the message names the step and rc."""


def latest_manifest_ts(entity: str) -> str | None:
    """Return the most-recent extracted_at_utc for an entity across all manifests."""
    candidates: list[str] = []
    # Base manifest
    base = EXPORT_DIR / f"{entity}.manifest.json"
    if base.exists():
        candidates.append(json.loads(base.read_text())["extracted_at_utc"])
    # Inc manifests
    for p in EXPORT_DIR.glob(f"{entity}_inc_*.manifest.json"):
        candidates.append(json.loads(p.read_text())["extracted_at_utc"])
    return max(candidates) if candidates else None


def find_latest_inc_prefix(entity: str, since_mono: float | None = None) -> str | None:
    """Most-recent inc_<timestamp> prefix for this entity.

    If since_mono is given (monotonic seconds), only consider files modified
    after that point — keeps stale prefixes from earlier runs out.
    """
    prefixes = set()
    for p in EXPORT_DIR.glob(f"{entity}_inc_*_part_*.csv"):
        if since_mono is not None and p.stat().st_mtime < since_mono:
            continue
        prefixes.add(p.name.rsplit("_part_", 1)[0])
    return max(prefixes) if prefixes else None


def run(cmd: list[str], dry_run: bool) -> int:
    print(f"\n$ {' '.join(cmd)}")
    if dry_run:
        return 0
    return subprocess.run(cmd, check=False).returncode


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--lookback-days", type=int, default=2,
                    help="Fallback lookback when no manifest exists (default 2d).")
    ap.add_argument("--dry-run", action="store_true",
                    help="Print commands without running them.")
    ap.add_argument("--skip-messages", action="store_true",
                    help="Don't refresh messages (saves time on partial refreshes).")
    args = ap.parse_args()

    import time
    run_started_mono = time.time() - 1  # 1s slop to avoid clock-edge misses
    now = datetime.now(timezone.utc)
    fallback = (now - timedelta(days=args.lookback_days)).strftime("%Y-%m-%dT%H:%M:%SZ")

    print("=" * 78)
    print(f"Daily refresh @ {now.isoformat()}")
    print("=" * 78)

    # ---- Plan ----
    incremental_entities = [
        ("Conversations", "conversations"),
        ("Opportunities", "opportunities"),
    ]

    print("\n=== Plan ===")
    plans: list[dict] = []
    for canonical, cli_name in incremental_entities:
        latest = latest_manifest_ts(canonical) or fallback
        plans.append({"canonical": canonical, "cli_name": cli_name, "since_iso": latest})
        print(f"  {canonical:18}  since {latest}")

    if not args.skip_messages:
        # Messages: refresh last lookback_days
        plans.append({"canonical": "ConversationMessages", "cli_name": "messages",
                      "since_days": args.lookback_days})
        print(f"  ConversationMessages   last {args.lookback_days} days")

    # ---- Extract ----
    for plan in plans:
        print(f"\n--- Extract: {plan['canonical']} ---")
        if "since_iso" in plan:
            cmd = [PYTHON, "-u", str(RUN_BATCH), plan["cli_name"], "--since-iso", plan["since_iso"]]
        else:
            # Messages: append to existing shards via --extend (don't wipe the 90d backfill).
            cmd = [PYTHON, "-u", str(RUN_BATCH), plan["cli_name"],
                   "--since-days", str(plan["since_days"]), "--extend"]
        rc = run(cmd, args.dry_run)
        if rc != 0:
            raise RefreshError(f"extract {plan['canonical']} failed (rc={rc})")

    # ---- Upsert ----
    for plan in plans:
        entity = plan["canonical"]
        if entity == "ConversationMessages":
            # Messages don't have inc_ prefix — they accumulate into the base shards.
            # Load via regular path with PK dedup.
            print(f"\n--- Load: {entity} (PK-dedup append) ---")
            rc = run([PYTHON, str(LOAD_SQL), "--skip-ddl", "--skip-views",
                      "--only", entity], args.dry_run)
        else:
            inc_prefix = find_latest_inc_prefix(entity, since_mono=run_started_mono)
            if not inc_prefix:
                print(f"\n--- Upsert: {entity} — no new inc files this run, skipping")
                continue
            print(f"\n--- Upsert: {entity} via {inc_prefix} ---")
            rc = run([PYTHON, str(LOAD_SQL), "--skip-ddl", "--skip-views",
                      "--upsert-glob", inc_prefix], args.dry_run)
        if rc != 0:
            raise RefreshError(f"upsert {entity} failed (rc={rc})")

    # ---- Rebuild ContactTags + smoke-test views ----
    print(f"\n--- Rebuild ContactTags + smoke views ---")
    if not args.dry_run:
        conn = connect(os.getenv("GHL_SQL_DATABASE", "dcr_warehouse"))
        cur = conn.cursor()
        cur.execute("TRUNCATE TABLE ghl.ContactTags;")
        cur.execute("""
            INSERT INTO ghl.ContactTags (ContactId, TagSlug)
            SELECT DISTINCT C.ContactId, LTRIM(RTRIM(LOWER(s.value)))
            FROM ghl.Contacts C
            CROSS APPLY STRING_SPLIT(ISNULL(C.Tags, ''), '|') AS s
            WHERE LTRIM(RTRIM(s.value)) <> ''
        """)
        cur.execute("SELECT COUNT_BIG(*) FROM ghl.ContactTags")
        print(f"  ContactTags rebuilt: {cur.fetchone()[0]:,} rows")
    rc = run([PYTHON, str(SMOKE_VIEWS)], args.dry_run)
    if rc != 0:
        raise RefreshError(f"smoke-views failed (rc={rc})")

    print(f"\nDONE @ {datetime.now(timezone.utc).isoformat()}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except RefreshError as e:
        send_alert("DCR refresh FAILED", f"{e}\nLog: {REPO_ROOT}/logs/refresh-err.log")
        sys.exit(1)
    except Exception:
        send_alert("DCR refresh CRASHED", traceback.format_exc())
        sys.exit(1)
