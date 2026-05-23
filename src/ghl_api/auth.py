from __future__ import annotations

from dataclasses import dataclass


@dataclass
class OAuthCredentials:
    client_id: str
    client_secret: str
    access_token: str
    refresh_token: str | None = None
    location_id: str | None = None
    company_id: str | None = None

    def auth_header(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.access_token}"}


@dataclass
class APIKeyCredentials:
    api_key: str

    def auth_header(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.api_key}"}
