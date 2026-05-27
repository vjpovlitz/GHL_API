"""POC: per-conversation first-response time, from local CSVs.

Mirrors sql/views/vw_ResponseTime.sql.

For each conversation with at least one inbound message:
    FirstInboundUtc        earliest inbound
    FirstOutboundAfterUtc  earliest outbound AFTER FirstInboundUtc
    ResponseSeconds        delta in seconds (or None if no outbound reply)
    ResponseBucket         <1min | <5min | <1hr | <1day | >=1day | no_reply

Outputs a bucket distribution.

Run:
    .venv/bin/python scripts/poc_response_time.py [--days 30]
"""
from __future__ import annotations

import argparse
import csv
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

EXPORT_DIR = Path(__file__).resolve().parent.parent / "data" / "exports"


def _parse_dt(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None


def _iter_csv(glob: str):
    for p in sorted(EXPORT_DIR.glob(glob)):
        with p.open(encoding="utf-8-sig", newline="") as f:
            yield from csv.DictReader(f)


def bucket(seconds: float | None) -> str:
    if seconds is None:
        return "no_reply"
    if seconds < 60:
        return "<1min"
    if seconds < 300:
        return "<5min"
    if seconds < 3600:
        return "<1hr"
    if seconds < 86400:
        return "<1day"
    return ">=1day"


BUCKET_ORDER = ["<1min", "<5min", "<1hr", "<1day", ">=1day", "no_reply"]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=30,
                    help="Only count convs with FirstInboundUtc within last N days. Default 30.")
    args = ap.parse_args()

    cutoff = datetime.now(timezone.utc) - timedelta(days=args.days)

    # Build per-conversation first inbound + first outbound after
    first_inbound: dict[str, datetime] = {}
    outbounds: dict[str, list[datetime]] = defaultdict(list)

    n_msgs = 0
    for r in _iter_csv("ConversationMessages_part_*.csv"):
        n_msgs += 1
        conv = r.get("ConversationId") or ""
        if not conv:
            continue
        dt = _parse_dt(r.get("DateAddedUtc"))
        if not dt:
            continue
        direction = r.get("Direction") or ""
        if direction == "inbound":
            cur = first_inbound.get(conv)
            if cur is None or dt < cur:
                first_inbound[conv] = dt
        elif direction == "outbound":
            outbounds[conv].append(dt)

    print(f"[response] scanned {n_msgs:,} messages")
    print(f"[response] convs with at least 1 inbound: {len(first_inbound):,}")

    # Per-conv: first outbound AFTER first inbound
    bucket_counts: dict[str, int] = {b: 0 for b in BUCKET_ORDER}
    response_seconds: list[int] = []
    in_window = 0

    for conv, fi in first_inbound.items():
        if fi < cutoff:
            continue
        in_window += 1
        outs = [t for t in outbounds.get(conv, []) if t > fi]
        if outs:
            first_out = min(outs)
            sec = int((first_out - fi).total_seconds())
            response_seconds.append(sec)
            bucket_counts[bucket(sec)] += 1
        else:
            bucket_counts["no_reply"] += 1

    print(f"[response] in window (last {args.days}d): {in_window:,} convs")
    print()

    # Distribution
    print(f"{'Bucket':10}  {'Count':>8}  {'Pct':>6}")
    print("-" * 30)
    total = sum(bucket_counts.values())
    for b in BUCKET_ORDER:
        c = bucket_counts[b]
        pct = 100.0 * c / total if total else 0
        print(f"{b:10}  {c:>8,}  {pct:>5.1f}%")
    print("-" * 30)
    print(f"{'TOTAL':10}  {total:>8,}")

    # Quick stats on response_seconds (excluding no_reply)
    if response_seconds:
        response_seconds.sort()
        n = len(response_seconds)
        p50 = response_seconds[n // 2]
        p90 = response_seconds[int(n * 0.9)]
        p99 = response_seconds[int(n * 0.99)]
        def fmt(s: int) -> str:
            if s < 60: return f"{s}s"
            if s < 3600: return f"{s // 60}m {s % 60}s"
            if s < 86400: return f"{s // 3600}h {(s % 3600) // 60}m"
            return f"{s // 86400}d {(s % 86400) // 3600}h"
        print()
        print(f"Response-time percentiles (replied convs only, n={n:,}):")
        print(f"  p50: {fmt(p50)}")
        print(f"  p90: {fmt(p90)}")
        print(f"  p99: {fmt(p99)}")

    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
