"""Pipelines resource — opportunity pipeline + stage definitions.

Endpoints:
    GET /opportunities/pipelines     — list pipelines for a location
"""
from __future__ import annotations

from typing import Any

from ghl_api.resources._base import Resource


class Pipelines(Resource):
    def list(self, *, location_id: str | None = None) -> dict[str, Any]:
        params = {"locationId": self._location(location_id)}
        return self._request("GET", "/opportunities/pipelines", params=params)
