from __future__ import annotations

from typing import Any

from ghl_api.resources._base import Resource


class Contacts(Resource):
    def list(
        self,
        *,
        location_id: str | None = None,
        limit: int = 20,
        query: str | None = None,
        start_after: str | None = None,
        start_after_id: str | None = None,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {
            "locationId": self._location(location_id),
            "limit": limit,
        }
        if query:
            params["query"] = query
        if start_after:
            params["startAfter"] = start_after
        if start_after_id:
            params["startAfterId"] = start_after_id
        return self._request("GET", "/contacts/", params=params)

    def search(
        self,
        *,
        location_id: str | None = None,
        filters: list[dict[str, Any]] | None = None,
        page_limit: int = 20,
        sort: list[dict[str, Any]] | None = None,
        search_after: list[Any] | None = None,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {
            "locationId": self._location(location_id),
            "pageLimit": page_limit,
        }
        if filters is not None:
            body["filters"] = filters
        if sort is not None:
            body["sort"] = sort
        if search_after is not None:
            body["searchAfter"] = search_after
        return self._request("POST", "/contacts/search", json=body)

    def get(self, contact_id: str) -> dict[str, Any]:
        return self._request("GET", f"/contacts/{contact_id}")

    def create(self, payload: dict[str, Any], *, location_id: str | None = None) -> dict[str, Any]:
        body = {"locationId": self._location(location_id), **payload}
        return self._request("POST", "/contacts/", json=body)

    def update(self, contact_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        return self._request("PUT", f"/contacts/{contact_id}", json=payload)

    def upsert(self, payload: dict[str, Any], *, location_id: str | None = None) -> dict[str, Any]:
        body = {"locationId": self._location(location_id), **payload}
        return self._request("POST", "/contacts/upsert", json=body)

    def delete(self, contact_id: str) -> dict[str, Any]:
        return self._request("DELETE", f"/contacts/{contact_id}")

    def add_tags(self, contact_id: str, tags: list[str]) -> dict[str, Any]:
        return self._request("POST", f"/contacts/{contact_id}/tags", json={"tags": tags})

    def remove_tags(self, contact_id: str, tags: list[str]) -> dict[str, Any]:
        return self._request("DELETE", f"/contacts/{contact_id}/tags", json={"tags": tags})
