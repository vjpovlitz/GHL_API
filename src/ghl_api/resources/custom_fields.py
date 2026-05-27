"""Custom Fields resource — definitions for contact + opportunity.

Endpoint:
    GET /locations/{location_id}/customFields    — all custom fields for a location
"""
from __future__ import annotations

from typing import Any

from ghl_api.resources._base import Resource


class CustomFields(Resource):
    def list(self, *, location_id: str | None = None, model: str | None = None) -> dict[str, Any]:
        """List custom fields. model='contact' or model='opportunity' filters by model."""
        loc = self._location(location_id)
        params: dict[str, Any] = {}
        if model:
            params["model"] = model
        return self._request("GET", f"/locations/{loc}/customFields", params=params)
