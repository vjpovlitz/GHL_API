# Setup on a new machine

For when you want to pick up this project on another box (gaming desktop,
laptop, second Mac, etc.) while the SQL Server stays on the Windows VM at
`<sql-server-tailnet-ip>,1433`.

## Prerequisites on the new machine

1. **Git** + GitHub access to `vjpovlitz/GHL_API`
2. **Python 3.13+**
3. **Tailscale** — installed and signed into the same tailnet as the
   Windows VM. Verify with `tailscale status` and look for the SQL Server host's IP.
4. **Microsoft ODBC Driver 18 for SQL Server**:
   - **Windows**: usually already there if you have any SQL tooling. If
     not: `winget install Microsoft.SQLServer.ODBCDriver` or download from
     Microsoft.
   - **macOS**: `brew tap microsoft/mssql-release && HOMEBREW_ACCEPT_EULA=Y brew install msodbcsql18 mssql-tools18`
   - **Linux**: see https://learn.microsoft.com/sql/connect/odbc/linux-mac/

## Clone + bootstrap

```bash
git clone https://github.com/vjpovlitz/GHL_API.git
cd GHL_API

# Python venv
python -m venv .venv
# Windows:
.venv\Scripts\activate
# macOS/Linux:
source .venv/bin/activate

pip install -e .
pip install pyodbc streamlit plotly pandas
```

## Configure `.env`

Copy `.env.example` to `.env` and fill in:

```bash
# GHL credentials (copy from the original machine or the GHL admin UI)
GHL_ACCESS_TOKEN=pit-...
GHL_LOCATION_ID=hoqjFDVlAeYXKPG5xAOX
GHL_API_VERSION=2021-07-28

# SQL Server on the Windows VM (via Tailscale)
GHL_SQL_SERVER=<sql-server-tailnet-ip>,1433
GHL_SQL_USER=sa
GHL_SQL_PASSWORD=<your-sa-password>
GHL_SQL_DATABASE=dcr_warehouse
```

> `.env` is gitignored. Never commit credentials.

## Verify connectivity

```bash
.venv/bin/python scripts/verify_sql_connection.py
```

Expect "OK warehouse looks healthy" with row counts for the existing
`ghl.*` tables.

If TCP probe fails:
- `tailscale ping smokestackwind11vm` to confirm tailnet routing
- On the VM, confirm `Get-NetTCPConnection -LocalPort 1433` shows Listen
- See WINDOWS_VM_SETUP.md if SQL Server config drifted

## Run things

```bash
# Run the dashboard
.venv/bin/streamlit run dashboard/app.py
# -> open http://localhost:8501

# Pull a delta from the GHL API and upsert
.venv/bin/python scripts/refresh_daily.py

# Run the 20 dashboard queries (validates view perf)
.venv/bin/python scripts/dashboard_queries.py

# Smoke-test all 8 views
.venv/bin/python scripts/smoke_views.py
```

## Where the data lives

| Component               | Where                                       |
|-------------------------|---------------------------------------------|
| SQL Server (warehouse)  | Windows VM, Tailscale `<sql-server-tailnet-ip>,1433`  |
| Database                | `dcr_warehouse`                             |
| Schemas                 | `ghl` (current), `fub` (future), `analytics`|
| CSV exports             | `data/exports/` on whichever machine ran the extract (gitignored — PII)|
| Manifests / checkpoints | Same                                        |

CSVs are intermediate artifacts: the extractor writes them, the loader
reads them. They don't need to be on every machine. If you want to skip
re-extracting on a new machine, copy `data/exports/` over manually.

## Day-to-day workflow

1. `scripts/refresh_daily.py` — pulls deltas, upserts via MERGE, rebuilds
   ContactTags, smoke-tests views. ~90 seconds when there's no new data.
2. Dashboard auto-picks up changes after the 5-minute `@st.cache_data`
   TTL expires (or click "Rerun" in Streamlit).

## Multi-machine notes

- Both this machine AND the Windows VM stay on Tailscale.
- Only one machine needs to run `refresh_daily.py` per cycle — the SQL
  Server is shared.
- The Streamlit dashboard can run on any machine; it just hits the same
  SQL Server.
- For a Follow Up Boss integration: add a new `src/fub_api/` package and
  load into the `fub` schema. Same warehouse, same dashboard joins.
