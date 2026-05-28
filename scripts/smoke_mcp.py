"""Smoke-test the DCR MCP server end-to-end through the read-only dcr_ro login.

Confirms three things after any change to src/dcr_mcp/:
  1. The FastMCP server module imports and every tool is registered.
  2. Schema + curated view-backed tools return real data via dcr_ro.
  3. The guardrails actually reject writes / out-of-set ORDER BY columns.

PII tools (contacts/messages) are executed but their rows are masked in output —
we assert shape + row count, never print lead names/emails/phones (DATA_RULES §7).

Exit 0 = all checks passed. Non-zero = at least one failed.
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

# config.py loads .env on import (MCP_SQL_* + GHL_SQL_*).
from dcr_mcp.db import run_select, validate_select  # noqa: E402
from dcr_mcp.schema import describe_schema, describe_table  # noqa: E402
from dcr_mcp.tools import (  # noqa: E402,F401
    REGISTRY,
    analytics,
    contacts,
    conversations,
    opportunities,
)

PASS, FAIL = "PASS", "FAIL"
results: list[tuple[str, str, str]] = []


def record(name: str, ok: bool, detail: str = "") -> None:
    results.append((PASS if ok else FAIL, name, detail))
    print(f"  [{PASS if ok else FAIL}] {name}{(' — ' + detail) if detail else ''}")


def is_table(out: str) -> bool:
    """A successful tool result is a markdown table, not a Rejected:/error string."""
    return out.lstrip().startswith("|")


def data_rows(out: str) -> int:
    """Count body rows in a markdown table (excludes header + separator)."""
    lines = [ln for ln in out.splitlines() if ln.startswith("|")]
    return max(0, len(lines) - 2)


def section(title: str) -> None:
    print(f"\n{'=' * 78}\n{title}\n{'=' * 78}")


def main() -> int:
    section("0. Server wiring (FastMCP registration)")
    try:
        from dcr_mcp.server import mcp  # imports => add_tool runs for every tool

        record("server module imports", True, f"FastMCP app: {mcp.name!r}")
        # REGISTRY (curated) + describe_schema + describe_table + run_select
        record("curated REGISTRY count", len(REGISTRY) == 14, f"{len(REGISTRY)} tools")
        names = sorted(f.__name__ for f in REGISTRY)
        print("    curated:", ", ".join(names))
    except Exception as e:  # noqa: BLE001
        record("server module imports", False, f"{type(e).__name__}: {e}")

    section("1. Schema grounding (read via dcr_ro)")
    sch = describe_schema()
    record("describe_schema", "Queryable objects" in sch and "ghl.Contacts" in sch,
           f"{len(sch)} chars")
    tbl = describe_table("Contacts")
    record("describe_table('Contacts')", "ContactId" in tbl, tbl.splitlines()[0])

    section("2. Analytics + pipeline tools (no PII — output shown)")
    no_pii = [
        ("list_pipelines", opportunities.list_pipelines),
        ("opportunities_by_stage", opportunities.opportunities_by_stage),
        ("agent_leaderboard", analytics.agent_leaderboard),
        ("lead_source_roi", analytics.lead_source_roi),
        ("daily_lead_funnel", analytics.daily_lead_funnel),
        ("funnel_cohort", analytics.funnel_cohort),
        ("response_time_summary", analytics.response_time_summary),
        ("message_heatmap", analytics.message_heatmap),
        ("tag_engagement", analytics.tag_engagement),
        ("activity_decay_summary", analytics.activity_decay_summary),
    ]
    for name, fn in no_pii:
        out = fn()
        ok = is_table(out)
        record(name, ok, f"{data_rows(out)} rows" if ok else out[:80])

    section("3. PII tools (executed, rows MASKED)")
    pii = [
        ("find_contact", lambda: contacts.find_contact("a", limit=5)),
        ("recent_conversations", lambda: conversations.recent_conversations(limit=5)),
        ("recent_messages", lambda: conversations.recent_messages(limit=5)),
        ("recent_opportunities", lambda: opportunities.recent_opportunities(limit=5)),
    ]
    for name, fn in pii:
        out = fn()
        ok = is_table(out) or "No rows matched" in out
        record(name, ok, f"{data_rows(out)} rows (masked)" if is_table(out) else out[:60])

    section("4. Free-SQL escape hatch (run_select)")
    agg = run_select("SELECT COUNT(*) AS Contacts FROM ghl.Contacts")
    record("run_select aggregate", is_table(agg), agg.replace("\n", " ")[:80])

    section("5. Guardrails (must REJECT)")
    rej = run_select("DELETE FROM ghl.Contacts")
    record("run_select rejects DELETE", rej.startswith("Rejected:"), rej[:70])
    multi = run_select("SELECT 1; DROP TABLE x")
    record("run_select rejects multi-statement", multi.startswith("Rejected:"), multi[:70])
    try:
        validate_select("SELECT * INTO bak FROM ghl.Contacts")
        record("validate_select blocks INTO", False, "did not raise")
    except ValueError:
        record("validate_select blocks INTO", True)
    try:
        analytics.agent_leaderboard(order_by="x]) DESC; DROP--")  # type: ignore[arg-type]
        record("order_by whitelist guard", False, "did not raise")
    except ValueError:
        record("order_by whitelist guard", True)

    section("Summary")
    fails = [r for r in results if r[0] == FAIL]
    print(f"  {len(results) - len(fails)}/{len(results)} checks passed.")
    if fails:
        for _, name, detail in fails:
            print(f"    FAIL: {name} — {detail}")
        return 1
    print("  All MCP smoke checks passed. OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
