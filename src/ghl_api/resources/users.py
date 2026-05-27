"""Users resource — agent/team-member directory.

Endpoints:
    GET /users/search                — list users; companyId-scoped (NOT locationId).
    GET /users/{id}                  — single user

PIT detail: /users/search requires `companyId` even for location-scoped tokens.
Set GHL_COMPANY_ID in .env or pass company_id= explicitly.
"""
from __future__ import annotations

from typing import Any

from ghl_api.auth import OAuthCredentials
from ghl_api.exceptions import GHLAPIError
from ghl_api.resources._base import Resource


class Users(Resource):
    def _company_id(self, override: str | None = None) -> str:
        if override:
            return override
        creds = self._client.credentials
        if isinstance(creds, OAuthCredentials) and creds.company_id:
            return creds.company_id
        raise GHLAPIError(
            "company_id is required for /users/search. "
            "Set GHL_COMPANY_ID in .env or pass company_id="
        )

    def search(
        self,
        *,
        company_id: str | None = None,
        location_id: str | None = None,
        query: str | None = None,
        ids: list[str] | None = None,
        skip: int = 0,
        limit: int = 100,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {
            "companyId": self._company_id(company_id),
            "skip": skip,
            "limit": limit,
        }
        if location_id:
            params["locationId"] = location_id
        if query:
            params["query"] = query
        if ids:
            params["ids"] = ",".join(ids)
        return self._request("GET", "/users/search", params=params)

    def get(self, user_id: str) -> dict[str, Any]:
        return self._request("GET", f"/users/{user_id}")
