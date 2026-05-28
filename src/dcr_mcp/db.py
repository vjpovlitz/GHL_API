"""Read-only query execution + guardrails + markdown formatting.

The read-only `dcr_ro` login is the hard safety boundary; the validation here is
defense-in-depth so the model gets a clear error instead of a SQL permission
failure, and so obviously-destructive intent never reaches the server.
"""
from __future__ import annotations

import datetime as _dt
import re
from decimal import Decimal
from typing import Any

import pyodbc

from .config import MAX_ROWS_CEILING, QUERY_TIMEOUT_SECONDS, ro_connection_string

# Whole-word tokens that must never appear in a read query. `into` blocks
# SELECT ... INTO (which writes a table); `waitfor` blocks WAITFOR DELAY (a DoS).
_FORBIDDEN = re.compile(
    r"\b(insert|update|delete|merge|drop|alter|create|truncate|exec|execute|"
    r"grant|revoke|deny|backup|restore|shutdown|reconfigure|into|openrowset|"
    r"openquery|opendatasource|waitfor|dbcc|kill)\b",
    re.IGNORECASE,
)
_PROC = re.compile(r"\b(sp|xp)_\w+", re.IGNORECASE)


def validate_select(sql: str) -> str:
    """Return a cleaned single SELECT/WITH statement or raise ValueError."""
    s = sql.strip().rstrip(";").strip()
    if not s:
        raise ValueError("Empty query.")
    if ";" in s:
        raise ValueError("Only a single statement is allowed (no ';').")
    low = s.lower()
    if not (low.startswith("select") or low.startswith("with")):
        raise ValueError("Only SELECT / WITH queries are allowed.")
    if _FORBIDDEN.search(s):
        raise ValueError(
            "Query contains a forbidden keyword. This endpoint is read-only: "
            "no writes, DDL, INTO, stored procedures, or WAITFOR."
        )
    if _PROC.search(s):
        raise ValueError("Stored-procedure calls (sp_/xp_) are not allowed.")
    return s


def run_readonly(
    sql: str, params: list[Any] | None = None, max_rows: int = 200
) -> tuple[list[str], list[list[Any]], bool]:
    """Execute a query as dcr_ro and return (columns, rows, truncated).

    Fetches at most `max_rows` (capped by MAX_ROWS_CEILING); `truncated` is True
    when more rows were available.
    """
    cap = max(1, min(max_rows, MAX_ROWS_CEILING))
    conn = pyodbc.connect(ro_connection_string(), autocommit=True)
    conn.timeout = QUERY_TIMEOUT_SECONDS
    try:
        cur = conn.cursor()
        cur.execute(sql, params or [])
        if cur.description is None:
            return [], [], False
        cols = [d[0] for d in cur.description]
        fetched = cur.fetchmany(cap + 1)
        truncated = len(fetched) > cap
        rows = [list(r) for r in fetched[:cap]]
        return cols, rows, truncated
    finally:
        conn.close()


def _fmt(v: Any) -> str:
    if v is None:
        return ""
    if isinstance(v, _dt.datetime):
        return v.isoformat(sep=" ")
    if isinstance(v, _dt.date):
        return v.isoformat()
    if isinstance(v, (Decimal, float)):
        f = float(v)
        if f == int(f):
            return str(int(f))
        return f"{f:.4f}".rstrip("0").rstrip(".")
    s = str(v).replace("\r", " ").replace("\n", " ").replace("|", "\\|").strip()
    return s if len(s) <= 80 else s[:77] + "..."


def to_markdown(
    cols: list[str], rows: list[list[Any]], truncated: bool, cap: int
) -> str:
    if not cols:
        return "Query ran but returned no result set."
    if not rows:
        return "No rows matched."
    head = "| " + " | ".join(cols) + " |"
    sep = "| " + " | ".join("---" for _ in cols) + " |"
    body = "\n".join("| " + " | ".join(_fmt(c) for c in r) + " |" for r in rows)
    note = f"\n\n_{len(rows)} row(s)._"
    if truncated:
        note = (
            f"\n\n_Showing first {len(rows)} row(s); result truncated at the "
            f"{cap}-row cap. Add filters or an aggregation to narrow it._"
        )
    return f"{head}\n{sep}\n{body}{note}"


def run_select(sql: str, max_rows: int = 200) -> str:
    """Validate + run an arbitrary read query, returned as a markdown table."""
    try:
        clean = validate_select(sql)
    except ValueError as e:
        return f"Rejected: {e}"
    try:
        cols, rows, truncated = run_readonly(clean, max_rows=max_rows)
    except pyodbc.Error as e:
        msg = str(e).split("]")[-1].strip()
        return f"SQL error: {msg}"
    return to_markdown(cols, rows, truncated, min(max_rows, MAX_ROWS_CEILING))
