"""Opportunities resource — GHL v2 pipeline/deal tracking.

Endpoints:
    GET  /opportunities/search       — list/search with cursor pagination
    GET  /opportunities/{id}         — single opportunity
    POST /opportunities/             — create
    PUT  /opportunities/{id}         — update
    DELETE /opportunities/{id}       — delete

Search uses page=N or after-cursor (lastModified+id). We use cursor pagination
because the backfill extractor needs deterministic ordering.
"""
from __future__ import annotations

from typing import Any

from ghl_api.resources._base import Resource


class Opportunities(Resource):
    def search(
        self,
        *,
        location_id: str | None = None,
        pipeline_id: str | None = None,
        pipeline_stage_id: str | None = None,
        contact_id: str | None = None,
        status: str | None = None,
        assigned_to: str | None = None,
        query: str | None = None,
        limit: int = 100,
        start_after: int | None = None,
        start_after_id: str | None = None,
        date: str | None = None,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {
            "location_id": self._location(location_id),
            "limit": limit,
        }
        if pipeline_id:
            params["pipeline_id"] = pipeline_id
        if pipeline_stage_id:
            params["pipeline_stage_id"] = pipeline_stage_id
        if contact_id:
            params["contact_id"] = contact_id
        if status:
            params["status"] = status
        if assigned_to:
            params["assigned_to"] = assigned_to
        if query:
            params["q"] = query
        if start_after is not None:
            params["startAfter"] = start_after
        if start_after_id:
            params["startAfterId"] = start_after_id
        if date:
            params["date"] = date
        return self._request("GET", "/opportunities/search", params=params)

    def get(self, opportunity_id: str) -> dict[str, Any]:
        return self._request("GET", f"/opportunities/{opportunity_id}")
