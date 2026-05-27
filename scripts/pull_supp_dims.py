"""Pull supplementary dimension data: Pipelines, PipelineStages, Users.

These are small datasets (tens of rows) — no need for the full batch framework.
One-shot CSV write + audit + manifest.

    .venv/bin/python scripts/pull_supp_dims.py [--only pipelines|users|calendars]
"""
from __future__ import annotations

import argparse
import csv
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from ghl_api import GHLClient  # noqa: E402
from ghl_api.manifest import Manifest  # noqa: E402
from ghl_api.mappers import (  # noqa: E402
    PIPELINE_COLUMNS,
    PIPELINE_STAGE_COLUMNS,
    USER_COLUMNS,
    map_pipeline,
    map_pipeline_stage,
    map_user,
)

EXPORT_DIR = REPO_ROOT / "data" / "exports"
AUDIT_SCRIPT = REPO_ROOT / "scripts" / "audit_csv.py"


def _now_utc_iso() -> str:
    n = datetime.now(timezone.utc)
    return n.strftime("%Y-%m-%dT%H:%M:%S.") + f"{n.microsecond // 1000:03d}Z"


def write_csv(filename: str, columns: list[str], rows: list[dict]) -> tuple[Path, int]:
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    path = EXPORT_DIR / filename
    path.write_bytes(b"\xef\xbb\xbf")
    with path.open("a", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=columns,
            lineterminator="\r\n",
            quoting=csv.QUOTE_MINIMAL,
            extrasaction="ignore",
        )
        writer.writeheader()
        for row in rows:
            writer.writerow({c: row.get(c, "") for c in columns})
    return path, len(rows)


def audit(paths: list[Path]) -> int:
    if not paths:
        return 0
    print(f"\n[audit] {len(paths)} file(s)")
    return subprocess.run(
        [sys.executable, str(AUDIT_SCRIPT), *[str(p) for p in paths]],
        check=False,
    ).returncode


def write_manifest(entity: str, columns: list[str], extracted_at: str, csv_paths: list[Path]) -> Path:
    mf = Manifest(
        entity=entity,
        columns=columns,
        extracted_at_utc=extracted_at,
        shard_size=0,
        output_dir=EXPORT_DIR,
    )
    for p in csv_paths:
        mf.add_shard(p)
    return mf.write()


def pull_pipelines(client: GHLClient, extracted_at: str) -> list[Path]:
    print("\n=== Pipelines + PipelineStages ===")
    loc = client.require_location_id()
    resp = client.pipelines.list()
    pipelines_raw = resp.get("pipelines") or []
    pipeline_rows = [map_pipeline(p, extracted_at=extracted_at) for p in pipelines_raw]
    stage_rows: list[dict] = []
    for p in pipelines_raw:
        for s in (p.get("stages") or []):
            stage_rows.append(
                map_pipeline_stage(
                    s,
                    pipeline_id=p.get("id", ""),
                    location_id=p.get("locationId") or loc,
                    extracted_at=extracted_at,
                )
            )
    p_path, p_n = write_csv("Pipelines_part_001.csv", PIPELINE_COLUMNS, pipeline_rows)
    s_path, s_n = write_csv("PipelineStages_part_001.csv", PIPELINE_STAGE_COLUMNS, stage_rows)
    print(f"  Pipelines:      {p_n} -> {p_path.name}")
    print(f"  PipelineStages: {s_n} -> {s_path.name}")
    return [p_path, s_path]


def pull_users(client: GHLClient, extracted_at: str) -> list[Path]:
    print("\n=== Users ===")
    all_users: list[dict] = []
    skip = 0
    while True:
        resp = client.users.search(skip=skip, limit=100)
        rows = resp.get("users") or []
        if not rows:
            break
        all_users.extend(rows)
        if len(rows) < 100:
            break
        skip += 100
    user_rows = [map_user(u, extracted_at=extracted_at) for u in all_users]
    path, n = write_csv("Users_part_001.csv", USER_COLUMNS, user_rows)
    print(f"  Users: {n} -> {path.name}")
    return [path]


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--only", choices=["pipelines", "users", "all"], default="all")
    args = p.parse_args()

    client = GHLClient.from_env()
    extracted_at = _now_utc_iso()

    all_paths: list[tuple[str, list[str], list[Path]]] = []

    if args.only in ("pipelines", "all"):
        paths = pull_pipelines(client, extracted_at)
        all_paths.append(("Pipelines", PIPELINE_COLUMNS, [paths[0]]))
        all_paths.append(("PipelineStages", PIPELINE_STAGE_COLUMNS, [paths[1]]))

    if args.only in ("users", "all"):
        paths = pull_users(client, extracted_at)
        all_paths.append(("Users", USER_COLUMNS, paths))

    # Combined audit run
    all_csvs = [p for _, _, paths in all_paths for p in paths]
    rc = audit(all_csvs)
    if rc != 0:
        print("\nAUDIT GATE FAILED")
        return rc

    for entity, columns, paths in all_paths:
        mf_path = write_manifest(entity, columns, extracted_at, paths)
        print(f"[{entity}] manifest -> {mf_path.name}")

    print(f"\n[throttle] {client.throttle.stats()}")
    print("OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
