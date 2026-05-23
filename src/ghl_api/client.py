from __future__ import annotations

import os
from typing import Any

import httpx
from dotenv import load_dotenv

from ghl_api.auth import APIKeyCredentials, OAuthCredentials
from ghl_api.exceptions import GHLAPIError, GHLAuthError, GHLRateLimitError
from ghl_api.resources.calendars import Calendars
from ghl_api.resources.contacts import Contacts
from ghl_api.resources.conversations import Conversations

V2_BASE_URL = "https://services.leadconnectorhq.com"
V1_BASE_URL = "https://rest.gohighlevel.com"
DEFAULT_API_VERSION = "2021-07-28"


class GHLClient:
    def __init__(
        self,
        credentials: OAuthCredentials | APIKeyCredentials,
        *,
        base_url: str = V2_BASE_URL,
        api_version: str = DEFAULT_API_VERSION,
        timeout: float = 30.0,
    ):
        self.credentials = credentials
        self.base_url = base_url.rstrip("/")
        self.api_version = api_version
        self._http = httpx.Client(timeout=timeout)

        self.contacts = Contacts(self)
        self.conversations = Conversations(self)
        self.calendars = Calendars(self)

    @property
    def default_location_id(self) -> str | None:
        if isinstance(self.credentials, OAuthCredentials):
            return self.credentials.location_id
        return None

    def require_location_id(self, override: str | None = None) -> str:
        loc = override or self.default_location_id
        if not loc:
            raise GHLAPIError("No location_id provided and none configured on client.")
        return loc

    @classmethod
    def from_env(cls, *, dotenv_path: str | None = None) -> GHLClient:
        load_dotenv(dotenv_path)
        access_token = os.getenv("GHL_ACCESS_TOKEN")
        if access_token:
            creds = OAuthCredentials(
                client_id=os.getenv("GHL_CLIENT_ID", ""),
                client_secret=os.getenv("GHL_CLIENT_SECRET", ""),
                access_token=access_token,
                refresh_token=os.getenv("GHL_REFRESH_TOKEN"),
                location_id=os.getenv("GHL_LOCATION_ID"),
                company_id=os.getenv("GHL_COMPANY_ID"),
            )
            return cls(creds, api_version=os.getenv("GHL_API_VERSION", DEFAULT_API_VERSION))

        api_key = os.getenv("GHL_API_KEY")
        if api_key:
            return cls(APIKeyCredentials(api_key=api_key), base_url=V1_BASE_URL)

        raise GHLAuthError("No GHL credentials found in environment.")

    def request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
    ) -> Any:
        url = f"{self.base_url}{path}"
        headers = {
            "Accept": "application/json",
            "Version": self.api_version,
            **self.credentials.auth_header(),
        }
        resp = self._http.request(method, url, params=params, json=json, headers=headers)
        return self._handle_response(resp)

    def _handle_response(self, resp: httpx.Response) -> Any:
        if resp.status_code == 401:
            raise GHLAuthError("Unauthorized", status_code=401, payload=_safe_json(resp))
        if resp.status_code == 429:
            retry_after = float(resp.headers.get("Retry-After", "0") or 0) or None
            raise GHLRateLimitError(
                "Rate limited", retry_after=retry_after, status_code=429, payload=_safe_json(resp)
            )
        if resp.status_code >= 400:
            raise GHLAPIError(
                f"GHL API error {resp.status_code}",
                status_code=resp.status_code,
                payload=_safe_json(resp),
            )
        if not resp.content:
            return None
        return resp.json()

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> GHLClient:
        return self

    def __exit__(self, *exc) -> None:
        self.close()


def _safe_json(resp: httpx.Response) -> dict:
    try:
        return resp.json()
    except Exception:
        return {"raw": resp.text}
