"""Connection config for the read-only MCP login.

Reuses GHL_SQL_SERVER / GHL_SQL_DATABASE (same VM + warehouse as the rest of the
project) but authenticates with the read-only MCP_SQL_* credentials so the LLM
can never mutate data even if a guardrail has a bug.
"""
from __future__ import annotations

import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

try:
    from dotenv import load_dotenv
    load_dotenv(REPO_ROOT / ".env")
except ImportError:
    pass

# Query timeout (seconds) applied to every read. Bounds runaway scans.
QUERY_TIMEOUT_SECONDS = int(os.getenv("MCP_QUERY_TIMEOUT", "30"))
# Hard ceiling on rows returned to the model, regardless of a tool's request.
MAX_ROWS_CEILING = int(os.getenv("MCP_MAX_ROWS", "500"))


def ro_connection_string() -> str:
    server = os.environ["GHL_SQL_SERVER"]
    database = os.getenv("GHL_SQL_DATABASE", "dcr_warehouse")
    user = os.environ["MCP_SQL_USER"]
    password = os.environ["MCP_SQL_PASSWORD"]
    return (
        "DRIVER={ODBC Driver 18 for SQL Server};"
        f"SERVER={server};UID={user};PWD={password};DATABASE={database};"
        "TrustServerCertificate=yes;Encrypt=no;"
    )
