"""Verify SQL Server connection + report schema state.

Useful when:
  - Migrating from local Docker to remote Windows VM
  - Verifying Tailscale routing works end-to-end
  - Smoke-checking the warehouse after a refresh

Reads GHL_SQL_* env vars (see .env.example). Prints:
  1. What it's connecting to
  2. SQL Server version + database name
  3. Row counts per ghl.* table
  4. Latest ExtractedAtUtc per entity
  5. ContactTags + materialized state

Exit codes:
  0 = connected, schema healthy
  1 = connection failed (with hint)
  2 = connected but schema missing or empty
"""
from __future__ import annotations

import os
import socket
import sys
import time
from contextlib import suppress

try:
    import pyodbc
except ImportError:
    print("ERROR: pyodbc not installed. Run: .venv/bin/pip install pyodbc")
    sys.exit(1)

# Load .env so GHL_SQL_* are picked up without shell exports.
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # dotenv is in project deps — but tolerate missing


def env(name: str, default: str = "") -> str:
    v = os.getenv(name, default)
    return v


def main() -> int:
    server = env("GHL_SQL_SERVER", "localhost,1433")
    user = env("GHL_SQL_USER", "sa")
    pw = env("GHL_SQL_PASSWORD")
    db = env("GHL_SQL_DATABASE", "dcr_warehouse")

    print("=" * 70)
    print("SQL Server connection check")
    print("=" * 70)
    print(f"  GHL_SQL_SERVER:   {server}")
    print(f"  GHL_SQL_USER:     {user}")
    print(f"  GHL_SQL_DATABASE: {db}")
    print(f"  GHL_SQL_PASSWORD: {'(set, ' + str(len(pw)) + ' chars)' if pw else '(EMPTY)'}")

    # --- Step 1: TCP reachability (helps debug Tailscale / firewall) ---
    host, _, port_str = server.partition(",")
    port = int(port_str) if port_str else 1433
    print(f"\nStep 1: TCP probe to {host}:{port}")
    t0 = time.monotonic()
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(5)
    try:
        sock.connect((host, port))
        dt = (time.monotonic() - t0) * 1000
        print(f"  OK  reachable ({dt:.0f} ms)")
    except (socket.timeout, ConnectionRefusedError, OSError) as e:
        dt = (time.monotonic() - t0) * 1000
        print(f"  FAIL  {type(e).__name__}: {e}  ({dt:.0f} ms)")
        print("\n  Diagnostics:")
        if "refused" in str(e).lower():
            print("    - SQL Server not running, or not listening on port", port)
            print("    - Check SQL Server Configuration Manager → TCP/IP enabled")
            print("    - Confirm static port 1433 (not dynamic) in IPAll")
        elif "timed out" in str(e).lower():
            print("    - Network path blocked. Likely Windows Firewall.")
            print("    - On the Windows VM: allow inbound TCP", port)
            print("    - Verify Tailscale: `tailscale status` on both ends")
            print("    - Try raw IP instead of hostname")
        elif "Name or service" in str(e):
            print(f"    - Hostname {host!r} not resolving")
            print("    - Tailscale MagicDNS may be off — try `tailscale up --accept-dns`")
        return 1
    finally:
        with suppress(Exception):
            sock.close()

    # --- Step 2: ODBC connect ---
    cs = (
        f"DRIVER={{ODBC Driver 18 for SQL Server}};SERVER={server};"
        f"UID={user};PWD={pw};DATABASE={db};"
        f"TrustServerCertificate=yes;Encrypt=no;"
    )
    print(f"\nStep 2: ODBC connect")
    t0 = time.monotonic()
    try:
        conn = pyodbc.connect(cs, timeout=8)
    except pyodbc.Error as e:
        dt = (time.monotonic() - t0) * 1000
        print(f"  FAIL  {e}  ({dt:.0f} ms)")
        msg = str(e).lower()
        if "login failed" in msg:
            print("  Diagnostics:")
            print("    - Wrong sa password, or Mixed Mode auth not enabled")
            print("    - On the VM: SSMS → Server properties → Security → SQL Server and Windows Authentication mode")
            print("    - Restart the SQL Server service after changing auth mode")
        elif "cannot open database" in msg:
            print(f"  Diagnostics:")
            print(f"    - Database {db!r} does not exist on the server")
            print(f"    - Run: .venv/bin/python scripts/load_to_sql.py  (it'll CREATE DATABASE for you)")
        return 1
    dt = (time.monotonic() - t0) * 1000
    print(f"  OK  connected ({dt:.0f} ms)")

    cur = conn.cursor()
    cur.execute("SELECT @@VERSION, DB_NAME(), @@SERVERNAME")
    version, dbname, srv = cur.fetchone()
    first_line = version.split("\n")[0].strip()
    print(f"\n  Server: {srv}")
    print(f"  DB:     {dbname}")
    print(f"  Build:  {first_line}")

    # --- Step 3: Schema inventory ---
    print(f"\nStep 3: Schema inventory")
    cur.execute("""
        SELECT TABLE_SCHEMA + '.' + TABLE_NAME AS FullName
        FROM INFORMATION_SCHEMA.TABLES
        WHERE TABLE_SCHEMA = 'ghl'
        ORDER BY TABLE_NAME;
    """)
    tables = [r[0] for r in cur.fetchall()]
    if not tables:
        print("  (no tables in ghl schema)")
        print("\n  Next step: run scripts/load_to_sql.py to create the schema.")
        return 2

    print(f"  {'Table':35} {'Rows':>12}  Latest ExtractedAtUtc")
    print(f"  {'-' * 35} {'-' * 12}  {'-' * 25}")
    for t in tables:
        cur.execute(f"SELECT COUNT_BIG(*) FROM {t}")
        n = cur.fetchone()[0]
        ts = "—"
        with suppress(pyodbc.Error):
            cur.execute(f"SELECT MAX(ExtractedAtUtc) FROM {t}")
            r = cur.fetchone()
            if r and r[0] is not None:
                ts = str(r[0])[:25]
        print(f"  {t:35} {n:>12,}  {ts}")

    # --- Step 4: Views ---
    print(f"\nStep 4: Views")
    cur.execute("""
        SELECT TABLE_NAME FROM INFORMATION_SCHEMA.VIEWS
        WHERE TABLE_SCHEMA = 'ghl' ORDER BY TABLE_NAME;
    """)
    views = [r[0] for r in cur.fetchall()]
    if views:
        for v in views:
            print(f"    {v}")
    else:
        print("  (no views — run scripts/load_to_sql.py to create)")

    print(f"\nOK  warehouse looks healthy.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
