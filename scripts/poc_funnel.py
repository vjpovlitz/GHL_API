"""POC: Daily Lead Funnel computed from local CSVs.

Mirrors sql/views/vw_DailyLeadFunnel.sql but runs locally so we can:
  1. Validate the funnel shape before SQL Server load.
  2. Sanity-check the SQL view row-for-row after load.

Stages (each contact counted at every stage they hit):
  [1] LeadsCreated      Contacts.csv: any row
  [2] EngagedContacts   any inbound message in ConversationMessages.csv
  [3] ApptsBooked       Appointments.csv row exists           (if file present)
  [4] ApptsShowed       Appointment.AppointmentStatus IN showed/confirmed/completed
  [5] OppsCreated       Opportunities.csv row exists          (if file present)
  [6] OppsWon           Opportunity.Status = 'won'

Run:
    .venv/bin/python scripts/poc_funnel.py [--days 90] [--by-source]
"""
from __future__ import annotations

import argparse
import csv
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

EXPORT_DIR = Path(__file__).resolve().parent.parent / "data" / "exports"


def _iter_csv(glob: str):
    """Yield rows from all matching shards. Empty if no files."""
    paths = sorted(EXPORT_DIR.glob(glob))
    for p in paths:
        with p.open(encoding="utf-8-sig", newline="") as f:
            yield from csv.DictReader(f)


def _parse_dt(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=90,
                    help="Only show LeadDate within last N days. Default 90.")
    ap.add_argument("--by-source", action="store_true",
                    help="Break funnel out by LeadSource. Otherwise aggregated.")
    args = ap.parse_args()

    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=args.days)

    # ---- Lead universe: ContactId -> (LeadDate, LeadSource)
    leads: dict[str, tuple[str, str]] = {}
    for r in _iter_csv("Contacts_part_*.csv"):
        dt = _parse_dt(r.get("DateAddedUtc"))
        if not dt:
            continue
        if dt < cutoff:
            continue
        cid = r.get("ContactId") or ""
        if not cid:
            continue
        src = r.get("Source") or "(unknown)"
        leads[cid] = (dt.date().isoformat(), src)

    print(f"[funnel] Lead universe in last {args.days} days: {len(leads):,} contacts")

    if not leads:
        print("No leads in the window — nothing to roll up.")
        return 0

    # ---- Conversations index: ConversationId -> ContactId
    conv_to_contact: dict[str, str] = {}
    for r in _iter_csv("Conversations_part_*.csv"):
        cid = r.get("ConversationId") or ""
        contact = r.get("ContactId") or ""
        if cid and contact:
            conv_to_contact[cid] = contact

    # ---- Engagement: first inbound msg per contact
    engaged: set[str] = set()
    for r in _iter_csv("ConversationMessages_part_*.csv"):
        if r.get("Direction") != "inbound":
            continue
        conv = r.get("ConversationId") or ""
        contact = conv_to_contact.get(conv) or r.get("ContactId") or ""
        if contact in leads:
            engaged.add(contact)

    # ---- Appointments (optional file)
    appts_booked: set[str] = set()
    appts_showed: set[str] = set()
    has_appt_file = bool(list(EXPORT_DIR.glob("Appointments_part_*.csv")))
    if has_appt_file:
        for r in _iter_csv("Appointments_part_*.csv"):
            contact = r.get("ContactId") or ""
            if contact not in leads:
                continue
            appts_booked.add(contact)
            status = (r.get("AppointmentStatus") or "").lower()
            if status in {"showed", "confirmed", "completed"}:
                appts_showed.add(contact)

    # ---- Opportunities (optional file)
    opps_created: set[str] = set()
    opps_won: set[str] = set()
    has_opp_file = bool(list(EXPORT_DIR.glob("Opportunities_part_*.csv")))
    if has_opp_file:
        for r in _iter_csv("Opportunities_part_*.csv"):
            contact = r.get("ContactId") or ""
            if contact not in leads:
                continue
            opps_created.add(contact)
            status = (r.get("Status") or "").lower()
            if status == "won":
                opps_won.add(contact)

    # ---- Roll up
    # Key = (LeadDate, LeadSource) if by_source else LeadDate
    Bucket = lambda: {"LeadsCreated": 0, "Engaged": 0, "Booked": 0,
                      "Showed": 0, "OppsCreated": 0, "OppsWon": 0}
    rollup: dict[tuple, dict] = defaultdict(Bucket)
    for contact, (lead_date, src) in leads.items():
        key = (lead_date, src) if args.by_source else (lead_date,)
        b = rollup[key]
        b["LeadsCreated"] += 1
        if contact in engaged:
            b["Engaged"] += 1
        if contact in appts_booked:
            b["Booked"] += 1
        if contact in appts_showed:
            b["Showed"] += 1
        if contact in opps_created:
            b["OppsCreated"] += 1
        if contact in opps_won:
            b["OppsWon"] += 1

    # ---- Print top-N report
    rows = sorted(rollup.items(), key=lambda kv: kv[0], reverse=True)

    if args.by_source:
        hdr = f"{'LeadDate':10}  {'Source':20}  {'Leads':>6}  {'Engd':>5}  {'Bookd':>5}  {'Showd':>5}  {'OppsC':>5}  {'Won':>4}  EngPct"
    else:
        hdr = f"{'LeadDate':10}  {'Leads':>6}  {'Engd':>5}  {'Bookd':>5}  {'Showd':>5}  {'OppsC':>5}  {'Won':>4}  EngPct"

    print()
    print(hdr)
    print("-" * len(hdr))

    totals = Bucket()
    shown = 0
    for key, b in rows:
        for k in totals:
            totals[k] += b[k]
        eng_pct = (100.0 * b["Engaged"] / b["LeadsCreated"]) if b["LeadsCreated"] else 0
        if args.by_source:
            print(f"{key[0]:10}  {key[1][:20]:20}  "
                  f"{b['LeadsCreated']:>6}  {b['Engaged']:>5}  {b['Booked']:>5}  "
                  f"{b['Showed']:>5}  {b['OppsCreated']:>5}  {b['OppsWon']:>4}  {eng_pct:5.1f}%")
        else:
            print(f"{key[0]:10}  "
                  f"{b['LeadsCreated']:>6}  {b['Engaged']:>5}  {b['Booked']:>5}  "
                  f"{b['Showed']:>5}  {b['OppsCreated']:>5}  {b['OppsWon']:>4}  {eng_pct:5.1f}%")
        shown += 1
        if shown >= 40 and not args.by_source:
            break

    print("-" * len(hdr))
    eng_pct = (100.0 * totals["Engaged"] / totals["LeadsCreated"]) if totals["LeadsCreated"] else 0
    print(f"{'TOTAL':10}  " + ("" if not args.by_source else f"{'(all sources)':20}  ") +
          f"{totals['LeadsCreated']:>6}  {totals['Engaged']:>5}  {totals['Booked']:>5}  "
          f"{totals['Showed']:>5}  {totals['OppsCreated']:>5}  {totals['OppsWon']:>4}  {eng_pct:5.1f}%")

    print()
    print(f"Files present:")
    print(f"  Contacts:              {bool(list(EXPORT_DIR.glob('Contacts_part_*.csv')))}")
    print(f"  Conversations:         {bool(list(EXPORT_DIR.glob('Conversations_part_*.csv')))}")
    print(f"  ConversationMessages:  {bool(list(EXPORT_DIR.glob('ConversationMessages_part_*.csv')))}")
    print(f"  Appointments:          {has_appt_file}  (Booked/Showed = 0 if missing)")
    print(f"  Opportunities:         {has_opp_file}  (OppsCreated/Won = 0 if missing)")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
