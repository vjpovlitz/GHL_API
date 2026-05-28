import datetime as dt
from decimal import Decimal

import pytest

from dcr_mcp.db import _fmt, to_markdown, validate_select


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT 1",
        "  select top 5 * from ghl.Contacts ",
        "WITH c AS (SELECT 1 AS x) SELECT x FROM c",
        "SELECT 1;",  # trailing semicolon is tolerated
    ],
)
def test_validate_select_accepts_reads(sql):
    cleaned = validate_select(sql)
    assert not cleaned.endswith(";")


@pytest.mark.parametrize(
    "sql",
    [
        "",
        "DELETE FROM ghl.Contacts",
        "UPDATE ghl.Contacts SET x = 1",
        "INSERT INTO ghl.Tags VALUES (1)",
        "DROP TABLE ghl.Contacts",
        "ALTER TABLE ghl.Contacts ADD x INT",
        "CREATE TABLE t (x INT)",
        "TRUNCATE TABLE ghl.Contacts",
        "EXEC sp_who",
        "SELECT * INTO backup FROM ghl.Contacts",  # INTO writes
        "SELECT 1; DROP TABLE t",  # multi-statement
        "WAITFOR DELAY '00:00:10'",
        "SELECT * FROM ghl.Contacts; SELECT 2",
    ],
)
def test_validate_select_rejects_writes_and_tricks(sql):
    with pytest.raises(ValueError):
        validate_select(sql)


def test_columns_like_created_at_not_falsely_blocked():
    # 'created_at' contains 'create' but must not trip the \bcreate\b guard.
    assert validate_select("SELECT created_at, updated_at FROM ghl.X")


def test_to_markdown_basic_and_truncation():
    cols = ["A", "B"]
    rows = [[1, "x"], [2, "y"]]
    md = to_markdown(cols, rows, truncated=False, cap=200)
    assert "| A | B |" in md and "| 1 | x |" in md
    assert "2 row(s)" in md

    md_trunc = to_markdown(cols, rows, truncated=True, cap=2)
    assert "truncated" in md_trunc and "2-row cap" in md_trunc

    assert "No rows matched" in to_markdown(cols, [], False, 200)
    assert "no result set" in to_markdown([], [], False, 200)


def test_curated_registry_is_wellformed():
    from dcr_mcp.tools import REGISTRY

    names = [f.__name__ for f in REGISTRY]
    assert len(names) == len(set(names)), f"duplicate tool names: {names}"
    assert len(names) >= 14, f"expected >=14 curated tools, got {len(names)}"
    for f in REGISTRY:
        assert (f.__doc__ or "").strip(), f"{f.__name__} is missing a docstring"


def test_order_by_is_whitelisted_before_interpolation():
    # order_by is interpolated into the SQL, so a value outside the Literal set
    # must be rejected before any query is built (no DB needed for this path).
    from dcr_mcp.tools.analytics import agent_leaderboard, lead_source_roi, tag_engagement

    for tool in (agent_leaderboard, lead_source_roi, tag_engagement):
        with pytest.raises(ValueError):
            tool(order_by="x]) DESC; DROP TABLE ghl.Contacts --")


def test_fmt_numbers_dates_and_text():
    assert _fmt(Decimal("0E-22")) == "0"
    assert _fmt(Decimal("0.00")) == "0"
    assert _fmt(6.763563102604) == "6.7636"
    assert _fmt(1234.0) == "1234"
    assert _fmt(None) == ""
    assert _fmt(dt.date(2026, 5, 27)) == "2026-05-27"
    assert _fmt("a|b") == "a\\|b"
    assert "\n" not in _fmt("x\r\ny") and "\r" not in _fmt("x\r\ny")
    assert _fmt("z" * 100).endswith("...")
