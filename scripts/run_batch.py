"""Batch extractor CLI.

Examples:
    # 1k contacts test (Step A)
    .venv/bin/python scripts/run_batch.py contacts --max-rows 1000

    # full contacts
    .venv/bin/python scripts/run_batch.py contacts

    # 1k conversations test (Step C)
    .venv/bin/python scripts/run_batch.py conversations --max-rows 1000

    # messages for conversations with lastMessageDate >= now-90d
    .venv/bin/python scripts/run_batch.py messages --since-days 90

Each run:
    1. Loads checkpoint (if present and not --no-resume).
    2. Extracts via the appropriate Extractor subclass.
    3. Audits all shards for the entity (subprocess to scripts/audit_csv.py).
    4. Writes a manifest with row counts + sha256 per shard.
    5. Exits non-zero if audit fails or row count is impossible.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from ghl_api import GHLClient  # noqa: E402
from ghl_api.batch import (  # noqa: E402
    AppointmentsExtractor,
    ContactsExtractor,
    ConversationsExtractor,
    MessagesExtractor,
    OpportunitiesExtractor,
)
from ghl_api.manifest import Manifest  # noqa: E402

EXPORT_DIR = REPO_ROOT / "data" / "exports"
AUDIT_SCRIPT = REPO_ROOT / "scripts" / "audit_csv.py"


def _iso_to_ms(iso: str) -> int:
    """Parse ISO 8601 into epoch milliseconds (UTC)."""
    s = iso.strip()
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return int(dt.astimezone(timezone.utc).timestamp() * 1000)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="GHL batch extractor")
    p.add_argument("entity", choices=["contacts", "conversations", "messages", "opportunities", "appointments"])
    p.add_argument("--max-rows", type=int, default=None,
                   help="Stop after this many rows. Default: unlimited.")
    p.add_argument("--shard-size", type=int, default=5000)
    p.add_argument("--page-limit", type=int, default=100)
    p.add_argument("--no-resume", action="store_true",
                   help="Ignore any existing checkpoint and restart.")
    p.add_argument("--since-days", type=int, default=90,
                   help="Messages only: pull conversations with lastMessageDate >= now-N days.")
    p.add_argument("--driver-min-days", type=int, default=None,
                   help="Messages only: only include convs with lastMessageDate <= now-N days. "
                        "Use with --since-days to express a delta window "
                        "(e.g. --since-days 30 --driver-min-days 7 = convs from 8..30 days ago).")
    p.add_argument("--max-driver-rows", type=int, default=None,
                   help="Messages only: cap the driver conversation list (for smoke tests).")
    p.add_argument("--extend", action="store_true",
                   help="Messages only: continue appending to existing shards using a NEW driver "
                        "list. Resets cursor=0, finished=False in the checkpoint while preserving "
                        "shard_index and rows_in_current_shard. Implies --resume semantics for shards.")
    p.add_argument("--since-iso", default=None,
                   help="Incremental: only include records updated >= this ISO timestamp. "
                        "For conversations: filters lastMessageDate. "
                        "For opportunities: filters updatedAt (client-side).")
    p.add_argument("--skip-audit", action="store_true",
                   help="Skip the audit gate (NOT recommended).")
    return p.parse_args()


def reset_outputs(entity_name: str) -> None:
    cp_path = EXPORT_DIR / f"{entity_name}.checkpoint.json"
    if cp_path.exists():
        cp_path.unlink()
    for p in EXPORT_DIR.glob(f"{entity_name}_part_*.csv"):
        p.unlink()
    mf = EXPORT_DIR / f"{entity_name}.manifest.json"
    if mf.exists():
        mf.unlink()


def driver_conversations_since(
    client: GHLClient,
    since_days: int,
    *,
    cap: int | None = None,
    min_days: int | None = None,
) -> list[dict]:
    """Pull conversation IDs+contactId+locationId for messages backfill.

    Window: [now-since_days, now-min_days] (inclusive on both ends).
    If min_days is None, the upper bound is now (i.e. no upper filter).
    """
    now = datetime.now(timezone.utc)
    cutoff_ms = int((now - timedelta(days=since_days)).timestamp() * 1000)
    upper_ms = int((now - timedelta(days=min_days)).timestamp() * 1000) if min_days else None
    print(f"[messages] driver: window = "
          f"[{datetime.fromtimestamp(cutoff_ms / 1000, tz=timezone.utc).isoformat()}, "
          f"{datetime.fromtimestamp(upper_ms / 1000, tz=timezone.utc).isoformat() if upper_ms else 'now'}] "
          f"(since-days={since_days}, min-days={min_days})")
    drivers: list[dict] = []
    cursor: tuple[str, str] | None = None
    page = 0
    while True:
        start_after_date, start_after_id = (cursor or (None, None))
        params = {
            "locationId": client.require_location_id(),
            "limit": 100,
            "sortBy": "last_message_date",
            "sort": "desc",
        }
        if start_after_date:
            params["startAfterDate"] = start_after_date
        if start_after_id:
            params["startAfterId"] = start_after_id
        resp = client.request("GET", "/conversations/search", params=params)
        rows = resp.get("conversations") or []
        if not rows:
            break
        # rows arrive newest-first; stop when we cross the cutoff.
        for r in rows:
            lmd = r.get("lastMessageDate")
            try:
                lmd_ms = int(lmd) if lmd else 0
            except (TypeError, ValueError):
                lmd_ms = 0
            if lmd_ms < cutoff_ms:
                page += 1
                print(f"[messages] driver: page={page} (lower cutoff hit) collected={len(drivers)}")
                return drivers
            if upper_ms is not None and lmd_ms > upper_ms:
                # Newer than upper bound — skip (already covered by a prior phase).
                continue
            drivers.append({
                "id": r.get("id"),
                "contactId": r.get("contactId", ""),
                "locationId": r.get("locationId", ""),
            })
            if cap is not None and len(drivers) >= cap:
                print(f"[messages] driver: cap hit at {cap}")
                return drivers
        page += 1
        last = rows[-1]
        cursor = (last.get("lastMessageDate"), last.get("id"))
        if len(rows) < params["limit"]:
            break
        print(f"[messages] driver: page={page} collected={len(drivers)}")
    return drivers


def run_audit(entity_name: str, shard_glob: str | None = None) -> int:
    glob_pat = shard_glob or f"{entity_name}_part_*.csv"
    paths = sorted(EXPORT_DIR.glob(glob_pat))
    if not paths:
        print(f"[{entity_name}] audit: no shard files to audit ({glob_pat})", flush=True)
        return 0
    print(f"[{entity_name}] audit: {len(paths)} shard(s) matching {glob_pat}", flush=True)
    sys.stdout.flush()
    result = subprocess.run(
        [sys.executable, str(AUDIT_SCRIPT), *[str(p) for p in paths]],
        check=False,
    )
    return result.returncode


def write_manifest(entity_name: str, columns: list[str], extracted_at: str, shard_size: int) -> Path:
    mf = Manifest(
        entity=entity_name,
        columns=columns,
        extracted_at_utc=extracted_at,
        shard_size=shard_size,
        output_dir=EXPORT_DIR,
    )
    for path in sorted(EXPORT_DIR.glob(f"{entity_name}_part_*.csv")):
        mf.add_shard(path)
    return mf.write()


def main() -> int:
    args = parse_args()
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)

    client = GHLClient.from_env()

    if args.entity == "contacts":
        entity_name = "Contacts"
        if args.no_resume:
            reset_outputs(entity_name)
        ex = ContactsExtractor(
            client,
            output_dir=EXPORT_DIR,
            shard_size=args.shard_size,
            page_limit=args.page_limit,
        )
        cp = ex.run(max_rows=args.max_rows, resume=not args.no_resume)
        columns = ex.columns

    elif args.entity == "conversations":
        entity_name = "Conversations"
        if args.no_resume:
            reset_outputs(entity_name)
        ex = ConversationsExtractor(
            client,
            output_dir=EXPORT_DIR,
            shard_size=args.shard_size,
            page_limit=args.page_limit,
        )
        # Incremental: pre-seed checkpoint cursor to (since_iso_as_ms, None) so the
        # extractor's startAfterDate paginates from that point forward.
        if args.since_iso:
            cutoff_ms = _iso_to_ms(args.since_iso)
            cp_path = EXPORT_DIR / f"{entity_name}.checkpoint.json"
            seed = {
                "entity": entity_name,
                "extracted_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z"),
                "cursor": [cutoff_ms - 1, None],
                "shard_index": 1,
                "rows_in_current_shard": 0,
                "rows_total": 0,
                "pages_fetched": 0,
                "finished": False,
                "shard_files": [],
            }
            cp_path.write_text(json.dumps(seed, indent=2), encoding="utf-8")
            # Force shard files to a per-run incremental prefix (captured once).
            ts_prefix = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            ex._shard_path = lambda idx, _p=ts_prefix: EXPORT_DIR / f"{entity_name}_inc_{_p}_part_{idx:03d}.csv"
            print(f"[conversations] incremental from {args.since_iso} (ms={cutoff_ms}, prefix=inc_{ts_prefix})")
        cp = ex.run(max_rows=args.max_rows, resume=not args.no_resume)
        columns = ex.columns

    elif args.entity == "messages":
        entity_name = "ConversationMessages"
        if args.no_resume:
            reset_outputs(entity_name)
        drivers = driver_conversations_since(
            client,
            args.since_days,
            cap=args.max_driver_rows,
            min_days=args.driver_min_days,
        )
        if not drivers:
            print("[messages] no driver conversations — nothing to do.")
            return 0
        print(f"[messages] driver list: {len(drivers)} conversations")
        # Persist driver list. If --extend, preserve prior driver lists as history.
        drv_path = EXPORT_DIR / "ConversationMessages.drivers.json"
        if args.extend and drv_path.exists():
            ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            drv_path.rename(EXPORT_DIR / f"ConversationMessages.drivers.{ts}.json")
        drv_path.write_text(json.dumps(drivers, indent=2), encoding="utf-8")

        # --extend: rewrite the checkpoint so we resume *with the new driver list*
        # but keep shard-state (so we append to the current shard).
        if args.extend:
            cp_path = EXPORT_DIR / f"{entity_name}.checkpoint.json"
            if cp_path.exists():
                cp_data = json.loads(cp_path.read_text(encoding="utf-8"))
                cp_data["cursor"] = 0
                cp_data["finished"] = False
                cp_data["pages_fetched"] = cp_data.get("pages_fetched", 0)
                cp_path.write_text(json.dumps(cp_data, indent=2), encoding="utf-8")
                print(f"[messages] --extend: checkpoint reset cursor=0, finished=False; "
                      f"keeping shard_index={cp_data.get('shard_index')} "
                      f"rows_in_current_shard={cp_data.get('rows_in_current_shard')}")

        ex = MessagesExtractor(
            client,
            conversations=drivers,
            output_dir=EXPORT_DIR,
            shard_size=args.shard_size,
            page_limit=args.page_limit,
        )
        cp = ex.run(max_rows=args.max_rows, resume=not args.no_resume)
        columns = ex.columns

    elif args.entity == "opportunities":
        entity_name = "Opportunities"
        if args.no_resume:
            reset_outputs(entity_name)
        ex = OpportunitiesExtractor(
            client,
            output_dir=EXPORT_DIR,
            shard_size=args.shard_size,
            page_limit=args.page_limit,
        )
        if args.since_iso:
            # /opportunities/search returns rows sorted desc by updatedAt by default.
            # We paginate normally but STOP at the first row older than the cutoff.
            # Wrap fetch_page to do that.
            cutoff_iso = args.since_iso.rstrip("Z").replace("Z", "")
            ts_prefix = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            ex._shard_path = lambda idx: EXPORT_DIR / f"{entity_name}_inc_{ts_prefix}_part_{idx:03d}.csv"
            original_fetch = ex.fetch_page
            def filtered_fetch(cursor):
                rows, next_cursor = original_fetch(cursor)
                kept = []
                for r in rows:
                    upd = r.get("updatedAt") or r.get("dateUpdated") or ""
                    if upd and upd >= cutoff_iso:
                        kept.append(r)
                    else:
                        # Crossed the cutoff (rows are desc by updatedAt) — stop here.
                        next_cursor = None
                        break
                return kept, next_cursor
            ex.fetch_page = filtered_fetch
            print(f"[opportunities] incremental from {args.since_iso}")
        cp = ex.run(max_rows=args.max_rows, resume=not args.no_resume)
        columns = ex.columns

    elif args.entity == "appointments":
        entity_name = "Appointments"
        if args.no_resume:
            reset_outputs(entity_name)
        # Pull calendar IDs from local Calendars dump if present, else fetch live.
        cal_ids: list[str] = []
        cals_resp = client.calendars.list()
        for c in (cals_resp.get("calendars") or []):
            cid = c.get("id")
            if cid:
                cal_ids.append(cid)
        if not cal_ids:
            print("[appointments] no calendars — nothing to do.")
            return 0
        now = datetime.now(timezone.utc)
        start_ms = int((now - timedelta(days=args.since_days)).timestamp() * 1000)
        end_ms = int(now.timestamp() * 1000)
        print(f"[appointments] {len(cal_ids)} calendars, window=last {args.since_days}d")
        ex = AppointmentsExtractor(
            client,
            calendar_ids=cal_ids,
            start_ms=start_ms,
            end_ms=end_ms,
            output_dir=EXPORT_DIR,
            shard_size=args.shard_size,
            page_limit=args.page_limit,
        )
        cp = ex.run(max_rows=args.max_rows, resume=not args.no_resume)
        columns = ex.columns

    else:
        print(f"unknown entity {args.entity!r}", file=sys.stderr)
        return 2

    print(f"\n[{entity_name}] extract done: "
          f"rows_total={cp.rows_total:,}  shards={len(cp.shard_files)}  "
          f"finished={cp.finished}")
    print(f"[{entity_name}] throttle: {client.throttle.stats()}")

    # ---- audit gate ----
    if not args.skip_audit:
        # If incremental, only audit the inc_* files from this run.
        audit_glob = None
        if args.since_iso and cp.shard_files:
            # Last shard file gives us the inc-prefix pattern
            inc_prefix = cp.shard_files[-1].split("_part_")[0]
            audit_glob = f"{inc_prefix}_part_*.csv"
        rc = run_audit(entity_name, shard_glob=audit_glob)
        if rc != 0:
            print(f"\n[{entity_name}] AUDIT GATE FAILED — see findings above.")
            return rc

    # ---- manifest ----
    if not args.since_iso:
        mf_path = write_manifest(entity_name, columns, cp.extracted_at_utc, args.shard_size)
        print(f"[{entity_name}] manifest -> {mf_path.name}")
    else:
        # Incremental: write a separate manifest tagged with the inc prefix
        inc_prefix = cp.shard_files[-1].split("_part_")[0] if cp.shard_files else f"{entity_name}_inc"
        from ghl_api.manifest import Manifest
        mf = Manifest(
            entity=inc_prefix,
            columns=columns,
            extracted_at_utc=cp.extracted_at_utc,
            shard_size=args.shard_size,
            output_dir=EXPORT_DIR,
        )
        for fname in cp.shard_files:
            mf.add_shard(EXPORT_DIR / fname)
        mf_path = mf.write()
        print(f"[{entity_name}] incremental manifest -> {mf_path.name}")
    print(f"[{entity_name}] OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
