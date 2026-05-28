"""Shared helpers + the curated-tool registry.

A tool is just a function decorated with @curated: it gets appended to REGISTRY,
which server.py registers with FastMCP. The function's type hints become the
tool's input schema and its docstring becomes the description the model reads —
so keep docstrings model-facing ("use this when ...").
"""
from __future__ import annotations

import datetime as _dt
from typing import Callable

import pyodbc

from ..db import MAX_ROWS_CEILING, run_readonly, to_markdown

REGISTRY: list[Callable[..., str]] = []


def curated(fn: Callable[..., str]) -> Callable[..., str]:
    """Register `fn` as a curated MCP tool."""
    REGISTRY.append(fn)
    return fn


def md(sql: str, params: list | None = None, cap: int = 200) -> str:
    """Run a read query and format as markdown, or a friendly error string."""
    try:
        cols, rows, truncated = run_readonly(sql, params=params, max_rows=cap)
    except pyodbc.Error as e:
        msg = str(e).split("]")[-1].strip()
        return f"Warehouse unavailable or query failed: {msg}"
    return to_markdown(cols, rows, truncated, min(cap, MAX_ROWS_CEILING))


def check_date(value: str, label: str) -> str:
    """Validate an ISO 'YYYY-MM-DD' date param; raise ValueError otherwise."""
    try:
        _dt.date.fromisoformat(value)
    except ValueError:
        raise ValueError(f"{label} must be an ISO date 'YYYY-MM-DD', got {value!r}.")
    return value


def check_choice(value: str, allowed: tuple[str, ...], label: str) -> str:
    """Whitelist `value` before it's interpolated into SQL (e.g. ORDER BY column).

    The MCP layer already validates Literal-typed params, but column names reach
    the query via f-string, so re-check here rather than trust the framework.
    """
    if value not in allowed:
        raise ValueError(f"{label} must be one of: {', '.join(allowed)}; got {value!r}.")
    return value
