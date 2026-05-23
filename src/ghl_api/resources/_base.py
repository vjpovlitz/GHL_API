from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ghl_api.client import GHLClient


class Resource:
    def __init__(self, client: GHLClient):
        self._client = client

    def _request(self, method: str, path: str, **kwargs):
        return self._client.request(method, path, **kwargs)

    def _location(self, override: str | None = None) -> str:
        return self._client.require_location_id(override)
