"""Sanitizers for SQL-Server-safe CSV output.

Single source of truth for cleaning field values. Every field that lands
in a CSV must go through the matching sanitizer here.

Rules enforced (see DATA_RULES.md section 2a):
- Newlines (CR/LF/CRLF), tabs -> single space
- NULL bytes and other C0 control chars -> stripped
- Unicode normalized to NFC
- Leading/trailing whitespace trimmed
- Internal runs of whitespace collapsed to single space
- Missing/None/null/NaN -> empty string
- Phones: keep + and digits, return as-is otherwise
- IDs: alphanumeric + dash + underscore only
"""
from __future__ import annotations

import re
import unicodedata
from datetime import datetime, timezone
from typing import Any

# Drop these (replace with empty string)
_C0_DROP_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")
# Replace these with a single space
_WS_REPLACE_RE = re.compile(r"[\r\n\t]+")
# Collapse internal whitespace
_MULTI_WS_RE = re.compile(r"\s{2,}")

_MISSING_TOKENS = {"none", "null", "nan", "undefined"}


def clean_text(v: Any, *, max_len: int | None = None, collapse_ws: bool = True) -> str:
    """Standard text sanitizer. SQL-Server safe.

    - Replaces any CR/LF/TAB with single space.
    - Removes NULL bytes and other C0 controls.
    - NFC normalizes Unicode.
    - Trims; optionally collapses internal whitespace.
    - Returns '' for None and for missing-token strings.
    - Truncates to max_len if provided.
    """
    if v is None:
        return ""
    if isinstance(v, bool):
        return "1" if v else "0"
    if isinstance(v, (list, tuple)):
        return "|".join(clean_text(x) for x in v if x is not None and x != "")
    if isinstance(v, dict):
        import json

        v = json.dumps(v, separators=(",", ":"), ensure_ascii=False)
    s = str(v)
    # Drop hard-bad chars
    s = _C0_DROP_RE.sub("", s)
    # Newlines / tabs -> space
    s = _WS_REPLACE_RE.sub(" ", s)
    # Unicode normalize
    s = unicodedata.normalize("NFC", s)
    # Collapse / trim
    if collapse_ws:
        s = _MULTI_WS_RE.sub(" ", s)
    s = s.strip()
    if s.lower() in _MISSING_TOKENS:
        return ""
    if max_len is not None and len(s) > max_len:
        s = s[:max_len]
    return s


def clean_id(v: Any) -> str:
    """Identifier: alphanumeric + dash + underscore. Empty if missing."""
    s = clean_text(v)
    return "".join(c for c in s if c.isalnum() or c in "-_")


def clean_phone(v: Any) -> str:
    """Phone: keep '+' and digits; pass through if non-empty."""
    if v is None:
        return ""
    s = str(v).strip()
    if not s:
        return ""
    cleaned = "+" + "".join(c for c in s if c.isdigit()) if s.startswith("+") else "".join(
        c for c in s if c.isdigit()
    )
    return cleaned if cleaned not in ("+", "") else ""


def clean_email(v: Any) -> str:
    s = clean_text(v).lower()
    return s if "@" in s else ("" if not s else s)


def clean_bit(v: Any) -> str:
    """Boolean -> '1' / '0' / '' (unknown)."""
    if v is None or v == "":
        return ""
    if isinstance(v, str):
        s = v.strip().lower()
        if s in ("1", "true", "t", "yes", "y"):
            return "1"
        if s in ("0", "false", "f", "no", "n"):
            return "0"
        return ""
    return "1" if bool(v) else "0"


def clean_int(v: Any) -> str:
    """Integer as string. Empty if missing/unparseable."""
    if v is None or v == "":
        return ""
    try:
        return str(int(v))
    except (ValueError, TypeError):
        try:
            return str(int(float(v)))
        except (ValueError, TypeError):
            return ""


def clean_utc_ts(v: Any) -> str:
    """ISO 8601 UTC w/ Z, ms precision. Empty if missing/unparseable.

    Accepts: ISO strings, epoch seconds, epoch milliseconds.
    """
    if v is None or v == "":
        return ""
    if isinstance(v, (int, float)) or (isinstance(v, str) and v.strip().lstrip("-").isdigit()):
        n = int(v)
        if abs(n) >= 10**12:
            n //= 1000
        try:
            dt = datetime.fromtimestamp(n, tz=timezone.utc)
        except (OverflowError, OSError, ValueError):
            return ""
        return dt.strftime("%Y-%m-%dT%H:%M:%S.000Z")
    s = str(v).strip()
    if not s:
        return ""
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        dt = dt.astimezone(timezone.utc)
        return dt.strftime("%Y-%m-%dT%H:%M:%S.") + f"{dt.microsecond // 1000:03d}Z"
    except ValueError:
        return ""


def clean_date(v: Any) -> str:
    """YYYY-MM-DD. Empty if missing/unparseable."""
    s = clean_text(v)
    return s[:10] if len(s) >= 10 else ""
