"""POC: opportunities by pipeline + stage — health of the active funnel.

Joins:  Opportunities  -> Pipelines  -> PipelineStages
Shows:  count of opps in each stage, by pipeline.

Useful for spotting:
  - Pipelines that have died (no recent opps)
  - Stages where opps pile up (bottlenecks)
  - The conversion ratio between stages

Run:
    .venv/bin/python scripts/poc_pipeline_health.py
"""
from __future__ import annotations

import csv
from collections import Counter, defaultdict
from pathlib import Path

EXPORT_DIR = Path(__file__).resolve().parent.parent / "data" / "exports"


def _iter_csv(glob: str):
    for p in sorted(EXPORT_DIR.glob(glob)):
        with p.open(encoding="utf-8-sig", newline="") as f:
            yield from csv.DictReader(f)


def main() -> int:
    # Pipelines: id -> name
    pipe_name: dict[str, str] = {}
    for r in _iter_csv("Pipelines_part_*.csv"):
        pipe_name[r["PipelineId"]] = r["Name"]

    # Stages: id -> (pipeline_id, position, name)
    stage_info: dict[str, tuple[str, int, str]] = {}
    for r in _iter_csv("PipelineStages_part_*.csv"):
        try:
            pos = int(r["Position"] or 0)
        except ValueError:
            pos = 0
        stage_info[r["PipelineStageId"]] = (r["PipelineId"], pos, r["Name"])

    # Opps
    by_pipe: Counter[str] = Counter()
    by_stage: Counter[tuple[str, str]] = Counter()    # (pipeline_id, stage_id)
    by_pipe_status: dict[str, Counter[str]] = defaultdict(Counter)
    n_opps = 0
    for r in _iter_csv("Opportunities_part_*.csv"):
        n_opps += 1
        pid = r["PipelineId"]
        sid = r["PipelineStageId"]
        status = r["Status"] or "(empty)"
        by_pipe[pid] += 1
        by_stage[(pid, sid)] += 1
        by_pipe_status[pid][status] += 1

    if n_opps == 0:
        print("No opportunities loaded yet.")
        return 0

    print(f"Total opportunities scanned: {n_opps:,}")
    print(f"Pipelines: {len(pipe_name)}    Stages: {len(stage_info)}")
    print()
    print("=" * 78)
    print("OPPS BY PIPELINE")
    print("=" * 78)
    for pid, count in by_pipe.most_common():
        name = pipe_name.get(pid, "(unknown pipeline)")
        statuses = by_pipe_status[pid]
        s_breakdown = "  ".join(f"{s}={c:,}" for s, c in statuses.most_common())
        print(f"  {count:>7,}  {name[:50]:50}  {s_breakdown}")

    print()
    print("=" * 78)
    print("OPPS BY STAGE (top 25)")
    print("=" * 78)
    rows = []
    for (pid, sid), c in by_stage.most_common():
        pname = pipe_name.get(pid, "?")[:30]
        sinfo = stage_info.get(sid)
        if sinfo:
            sname = sinfo[2][:40]
        else:
            sname = "(unknown stage)"
        rows.append((c, pname, sname))
    for c, p, s in rows[:25]:
        print(f"  {c:>7,}  pipeline={p:30}  stage={s}")

    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
