"""Pipeline + opportunity tools over ghl.Opportunities / Pipelines / PipelineStages."""
from __future__ import annotations

from typing import Literal

from .base import curated, md

OppStatus = Literal["open", "won", "lost", "abandoned"]


@curated
def list_pipelines() -> str:
    """List sales pipelines with their stage count and total opportunities.

    Use to discover pipeline names (call this before opportunities_by_stage) or
    for "what pipelines do we have".
    """
    # COUNT(DISTINCT ...) on both joins: the stage + opportunity joins otherwise
    # fan out into a cartesian product (stages x opps) and inflate the counts.
    sql = (
        "SELECT p.Name AS Pipeline, COUNT(DISTINCT s.PipelineStageId) AS Stages, "
        "COUNT(DISTINCT o.OpportunityId) AS Opportunities FROM ghl.Pipelines p "
        "LEFT JOIN ghl.PipelineStages s ON s.PipelineId = p.PipelineId "
        "LEFT JOIN ghl.Opportunities o ON o.PipelineId = p.PipelineId "
        "GROUP BY p.Name ORDER BY Opportunities DESC"
    )
    return md(sql, cap=50)


@curated
def opportunities_by_stage(
    pipeline: str | None = None, status: OppStatus | None = None
) -> str:
    """Opportunity counts and total value per pipeline stage.

    Use for "how many deals in each stage", "pipeline breakdown", "where are deals
    stuck". Optional `pipeline` name (see list_pipelines) and `status` filter.
    Ordered by pipeline then stage position.
    """
    where = []
    params: list = []
    if pipeline:
        where.append("p.Name = ?")
        params.append(pipeline)
    if status:
        where.append("o.Status = ?")
        params.append(status)
    clause = ("WHERE " + " AND ".join(where) + " ") if where else ""
    sql = (
        "SELECT p.Name AS Pipeline, s.Name AS Stage, s.Position, "
        "COUNT(*) AS Opps, SUM(o.MonetaryValue) AS TotalValue "
        "FROM ghl.Opportunities o "
        "JOIN ghl.PipelineStages s ON s.PipelineStageId = o.PipelineStageId "
        "JOIN ghl.Pipelines p ON p.PipelineId = o.PipelineId "
        f"{clause}GROUP BY p.Name, s.Name, s.Position ORDER BY p.Name, s.Position"
    )
    return md(sql, params, cap=200)


@curated
def recent_opportunities(limit: int = 10, status: OppStatus | None = None) -> str:
    """Most recently created opportunities (deals), newest first.

    Use for "latest deals", "new opportunities this week", "recent won deals"
    (with status='won'). Shows deal name, status, value, contact, pipeline + stage.
    """
    limit = max(1, min(limit, 200))
    where = ""
    params: list = [limit]
    if status:
        where = "WHERE o.Status = ? "
        params.append(status)
    sql = (
        "SELECT TOP (?) o.Name, o.Status, o.MonetaryValue, c.FullName AS Contact, "
        "p.Name AS Pipeline, s.Name AS Stage, o.DateAddedUtc "
        "FROM ghl.Opportunities o "
        "LEFT JOIN ghl.Contacts c ON c.ContactId = o.ContactId "
        "LEFT JOIN ghl.PipelineStages s ON s.PipelineStageId = o.PipelineStageId "
        "LEFT JOIN ghl.Pipelines p ON p.PipelineId = o.PipelineId "
        f"{where}ORDER BY o.DateAddedUtc DESC"
    )
    return md(sql, params, cap=limit)
