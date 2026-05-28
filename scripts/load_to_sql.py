"""Load all *_part_*.csv shards into SQL Server.

Connects via pyodbc + ODBC Driver 18, runs DDL, then bulk-inserts each
CSV via executemany with fast_executemany=True (effectively BULK INSERT
without needing the file on the server filesystem).

Usage:
    .venv/bin/python scripts/load_to_sql.py            # connects to localhost:1433
    .venv/bin/python scripts/load_to_sql.py --truncate # truncate tables first
    .venv/bin/python scripts/load_to_sql.py --skip-ddl # skip create_tables run

Env (optional):
    GHL_SQL_SERVER   default: localhost,1433
    GHL_SQL_USER     default: sa
    GHL_SQL_PASSWORD default: GhlDev_PassW0rd!
    GHL_SQL_DATABASE default: dcr_warehouse
"""
from __future__ import annotations

import argparse
import csv
import os
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# Load .env so GHL_SQL_* are picked up without shell exports.
try:
    from dotenv import load_dotenv
    load_dotenv(REPO_ROOT / ".env")
except ImportError:
    pass

try:
    import pyodbc
except ImportError:
    print("pyodbc not installed. Run: .venv/bin/pip install pyodbc")
    sys.exit(1)

EXPORT_DIR = REPO_ROOT / "data" / "exports"
SQL_DDL = REPO_ROOT / "sql" / "create_tables.sql"
VIEWS_DIR = REPO_ROOT / "sql" / "views"

# Map CSV file pattern -> (target_table, columns, datetime_cols, bit_cols, int_cols, pk)
# Order matters because of FKs (not enforced today, but ordered logically).
# `pk` enables client-side dedup across shards (E1+E2+E3 boundary convs can overlap).
LOAD_PLAN: list[dict] = [
    {
        "table": "ghl.Contacts",
        "glob": "Contacts_part_*.csv",
        "pk": "ContactId",
        "datetime_cols": {"DateAddedUtc", "DateUpdatedUtc", "ExtractedAtUtc"},
        "date_cols": {"DateOfBirth"},
        "bit_cols": set(),
        "int_cols": set(),
    },
    {
        "table": "ghl.Conversations",
        "glob": "Conversations_part_*.csv",
        "pk": "ConversationId",
        "datetime_cols": {"LastMessageDateUtc", "DateAddedUtc", "DateUpdatedUtc", "ExtractedAtUtc"},
        "date_cols": set(),
        "bit_cols": {"IsUnread", "IsStarred"},
        "int_cols": {"UnreadCount"},
    },
    {
        "table": "ghl.ConversationMessages",
        "glob": "ConversationMessages_part_*.csv",
        "pk": "MessageId",
        "datetime_cols": {"DateAddedUtc", "ExtractedAtUtc"},
        "date_cols": set(),
        "bit_cols": {"HasAttachment"},
        "int_cols": set(),
    },
    {
        "table": "ghl.Users",
        "glob": "Users_part_*.csv",
        "pk": "UserId",
        "datetime_cols": {"DateAddedUtc", "ExtractedAtUtc"},
        "date_cols": set(),
        "bit_cols": {"IsActive"},
        "int_cols": set(),
    },
    {
        "table": "ghl.Pipelines",
        "glob": "Pipelines_part_*.csv",
        "pk": "PipelineId",
        "datetime_cols": {"DateAddedUtc", "DateUpdatedUtc", "ExtractedAtUtc"},
        "date_cols": set(),
        "bit_cols": set(),
        "int_cols": set(),
    },
    {
        "table": "ghl.PipelineStages",
        "glob": "PipelineStages_part_*.csv",
        "pk": "PipelineStageId",
        "datetime_cols": {"ExtractedAtUtc"},
        "date_cols": set(),
        "bit_cols": {"ShowInFunnel", "ShowInPieChart"},
        "int_cols": {"Position"},
    },
    {
        "table": "ghl.Opportunities",
        "glob": "Opportunities_part_*.csv",
        "pk": "OpportunityId",
        "datetime_cols": {"DateAddedUtc", "DateUpdatedUtc", "DateLastStageChangeUtc",
                          "DateClosedUtc", "ExtractedAtUtc"},
        "date_cols": set(),
        "bit_cols": set(),
        "int_cols": set(),
        "decimal_cols": {"MonetaryValue"},
    },
    {
        "table": "ghl.Appointments",
        "glob": "Appointments_part_*.csv",
        "pk": "AppointmentId",
        "datetime_cols": {"StartTimeUtc", "EndTimeUtc", "DateAddedUtc",
                          "DateUpdatedUtc", "ExtractedAtUtc"},
        "date_cols": set(),
        "bit_cols": set(),
        "int_cols": set(),
    },
    {
        "table": "ghl.Tags",
        "glob": "Tags_part_*.csv",
        "pk": "TagId",
        "datetime_cols": {"FirstSeenAtUtc", "LastSeenAtUtc", "ExtractedAtUtc"},
        "date_cols": set(),
        "bit_cols": set(),
        "int_cols": {"ContactsCount"},
    },
    {
        "table": "ghl.CustomFields",
        "glob": "CustomFields_part_*.csv",
        "pk": "CustomFieldId",
        "datetime_cols": {"DateAddedUtc", "ExtractedAtUtc"},
        "date_cols": set(),
        "bit_cols": {"IsRequired"},
        "int_cols": {"Position"},
    },
]


def connect(database: str | None = None) -> pyodbc.Connection:
    server = os.getenv("GHL_SQL_SERVER", "localhost,1433")
    user = os.getenv("GHL_SQL_USER", "sa")
    pw = os.getenv("GHL_SQL_PASSWORD", "GhlDev_PassW0rd!")
    db = database or os.getenv("GHL_SQL_DATABASE", "master")
    cs = (
        f"DRIVER={{ODBC Driver 18 for SQL Server}};"
        f"SERVER={server};UID={user};PWD={pw};"
        f"DATABASE={db};"
        f"TrustServerCertificate=yes;Encrypt=no;"
    )
    return pyodbc.connect(cs, autocommit=True)


def ensure_database(db_name: str) -> None:
    with connect("master") as conn:
        cur = conn.cursor()
        cur.execute(f"IF DB_ID('{db_name}') IS NULL CREATE DATABASE [{db_name}]")
    print(f"  ensured database [{db_name}]")


def split_sql_batches(sql: str) -> list[str]:
    """Split T-SQL by GO statements (case-insensitive, on its own line)."""
    out: list[str] = []
    buf: list[str] = []
    for line in sql.splitlines():
        if line.strip().upper() == "GO":
            stmt = "\n".join(buf).strip()
            if stmt:
                out.append(stmt)
            buf = []
        else:
            buf.append(line)
    tail = "\n".join(buf).strip()
    if tail:
        out.append(tail)
    return out


def run_sql_file(conn: pyodbc.Connection, path: Path) -> None:
    print(f"  running {path.name}")
    cur = conn.cursor()
    for stmt in split_sql_batches(path.read_text(encoding="utf-8")):
        cur.execute(stmt)


def _convert_value(val: str, col_name: str, plan: dict):
    if val == "":
        return None
    if col_name in plan["datetime_cols"]:
        # CSV format: 2026-05-23T19:21:43.743Z
        return val.rstrip("Z").replace("T", " ") if val else None
    if col_name in plan["date_cols"]:
        return val[:10]
    if col_name in plan["bit_cols"]:
        return 1 if val == "1" else (0 if val == "0" else None)
    if col_name in plan["int_cols"]:
        try:
            return int(val)
        except ValueError:
            return None
    if col_name in plan.get("decimal_cols", set()):
        try:
            return float(val)
        except ValueError:
            return None
    return val


def load_table(conn: pyodbc.Connection, plan: dict, truncate: bool, batch_size: int = 1000,
               incremental_glob: str | None = None) -> int:
    glob_pat = incremental_glob if incremental_glob else plan["glob"]
    paths = sorted(EXPORT_DIR.glob(glob_pat))
    if not paths:
        print(f"  {plan['table']}: no shards found ({glob_pat})", flush=True)
        return 0

    cur = conn.cursor()
    cur.fast_executemany = True

    if truncate:
        cur.execute(f"TRUNCATE TABLE {plan['table']}")

    pk_col = plan.get("pk")
    seen_pks: set[str] = set()
    # If not truncating, seed with what's already in the table (idempotent reruns).
    if not truncate and pk_col:
        cur.execute(f"SELECT {pk_col} FROM {plan['table']}")
        for (pk,) in cur.fetchall():
            seen_pks.add(pk)
        if seen_pks:
            print(f"  {plan['table']}: skipping {len(seen_pks):,} PKs already loaded", flush=True)

    total_inserted = 0
    total_skipped = 0
    t0 = time.monotonic()

    for shard in paths:
        with shard.open(encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            cols = reader.fieldnames or []
            placeholders = ",".join(["?"] * len(cols))
            sql = f"INSERT INTO {plan['table']} ({','.join(cols)}) VALUES ({placeholders})"

            batch: list[tuple] = []
            for row in reader:
                if pk_col:
                    pk_val = row.get(pk_col, "")
                    if pk_val in seen_pks:
                        total_skipped += 1
                        continue
                    seen_pks.add(pk_val)
                values = tuple(_convert_value(row[c], c, plan) for c in cols)
                batch.append(values)
                if len(batch) >= batch_size:
                    cur.executemany(sql, batch)
                    total_inserted += len(batch)
                    batch = []
            if batch:
                cur.executemany(sql, batch)
                total_inserted += len(batch)

        dt = time.monotonic() - t0
        print(f"  {plan['table']}: {total_inserted:>9,} rows  "
              f"(skipped {total_skipped:,} dups, {dt:5.1f}s)", flush=True)

    return total_inserted


def upsert_table(conn: pyodbc.Connection, plan: dict, glob_pat: str, batch_size: int = 1000) -> int:
    """Load incremental shards via staging table + MERGE for true upsert."""
    paths = sorted(EXPORT_DIR.glob(glob_pat))
    if not paths:
        print(f"  {plan['table']}: no shards found ({glob_pat})", flush=True)
        return 0

    cur = conn.cursor()
    cur.fast_executemany = True

    # Read columns from first shard
    with paths[0].open(encoding="utf-8-sig", newline="") as f:
        cols = csv.DictReader(f).fieldnames or []

    # Build staging table (same schema as target, no PK)
    staging = f"##stg_{plan['table'].split('.')[-1]}"
    cur.execute(f"IF OBJECT_ID('tempdb..{staging}') IS NOT NULL DROP TABLE {staging}")
    cur.execute(f"SELECT TOP 0 * INTO {staging} FROM {plan['table']}")

    # Bulk insert into staging
    placeholders = ",".join(["?"] * len(cols))
    insert_sql = f"INSERT INTO {staging} ({','.join(cols)}) VALUES ({placeholders})"
    total_staged = 0
    seen_pks: set[str] = set()
    pk_col = plan.get("pk")

    for shard in paths:
        with shard.open(encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            batch: list[tuple] = []
            for row in reader:
                if pk_col:
                    pk_val = row.get(pk_col, "")
                    if pk_val in seen_pks:
                        continue
                    seen_pks.add(pk_val)
                values = tuple(_convert_value(row[c], c, plan) for c in cols)
                batch.append(values)
                if len(batch) >= batch_size:
                    cur.executemany(insert_sql, batch)
                    total_staged += len(batch)
                    batch = []
            if batch:
                cur.executemany(insert_sql, batch)
                total_staged += len(batch)

    print(f"  {plan['table']}: staged {total_staged:,} rows", flush=True)

    # MERGE staging into target
    update_set = ",".join(f"T.{c}=S.{c}" for c in cols if c != pk_col)
    insert_cols = ",".join(cols)
    insert_vals = ",".join(f"S.{c}" for c in cols)
    merge_sql = f"""
        MERGE {plan['table']} AS T
        USING {staging} AS S ON T.{pk_col} = S.{pk_col}
        WHEN MATCHED THEN UPDATE SET {update_set}
        WHEN NOT MATCHED THEN INSERT ({insert_cols}) VALUES ({insert_vals});
    """
    cur.execute(merge_sql)
    inserted = cur.rowcount
    cur.execute(f"DROP TABLE {staging}")
    print(f"  {plan['table']}: MERGE affected {inserted:,} rows", flush=True)
    return total_staged


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--truncate", action="store_true", help="TRUNCATE tables before insert")
    ap.add_argument("--skip-ddl", action="store_true", help="Skip create_tables.sql")
    ap.add_argument("--skip-views", action="store_true", help="Skip CREATE VIEW")
    ap.add_argument("--only", help="Load only one table (glob prefix, e.g. 'Pipelines')")
    ap.add_argument("--upsert-glob", help="Run UPSERT (MERGE) on shards matching this glob prefix "
                                          "(e.g. 'Conversations_inc_20260524'). Must match exactly one table.")
    ap.add_argument("--batch-size", type=int, default=1000)
    args = ap.parse_args()

    db_name = os.getenv("GHL_SQL_DATABASE", "dcr_warehouse")
    print(f"=== Connect ===")
    ensure_database(db_name)

    with connect(db_name) as conn:
        cur = conn.cursor()
        cur.execute("SELECT @@VERSION, DB_NAME()")
        version, db = cur.fetchone()
        print(f"  version: {version.split(chr(10))[0]}")
        print(f"  database: {db}")

        if not args.skip_ddl:
            print(f"\n=== DDL ===")
            run_sql_file(conn, SQL_DDL)

        if args.upsert_glob:
            print(f"\n=== Upsert (MERGE) — glob: {args.upsert_glob}* ===")
            # Match the upsert-glob against table.glob prefix (e.g. "Conversations_inc_..." matches "Conversations")
            for plan in LOAD_PLAN:
                base = plan["glob"].replace("_part_*.csv", "")
                if args.upsert_glob.startswith(base):
                    upsert_table(conn, plan, f"{args.upsert_glob}*.csv", batch_size=args.batch_size)
                    break
            else:
                print(f"  no LOAD_PLAN matched prefix {args.upsert_glob}")
            return 0

        print(f"\n=== Load ===")
        loaded: dict[str, int] = {}
        for plan in LOAD_PLAN:
            if args.only and not plan["glob"].startswith(args.only):
                continue
            n = load_table(conn, plan, args.truncate, batch_size=args.batch_size)
            loaded[plan["table"]] = n

        print(f"\n=== Row counts ===")
        for plan in LOAD_PLAN:
            if args.only and not plan["glob"].startswith(args.only):
                continue
            cur.execute(f"SELECT COUNT_BIG(*) FROM {plan['table']}")
            n = cur.fetchone()[0]
            tag = " ✓" if loaded.get(plan["table"], 0) == n else "  (already had data)"
            print(f"  {plan['table']:35} {n:>10,}{tag}")

        if not args.skip_views:
            print(f"\n=== Views ===")
            for vw in sorted(VIEWS_DIR.glob("*.sql")):
                run_sql_file(conn, vw)
    print("\nOK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
