import pytest

from ghl_api import GHLAuthError, GHLClient
from ghl_api.auth import OAuthCredentials


def test_oauth_credentials_auth_header():
    creds = OAuthCredentials(
        client_id="cid", client_secret="cs", access_token="tok"
    )
    assert creds.auth_header() == {"Authorization": "Bearer tok"}


def test_from_env_requires_credentials(monkeypatch):
    for k in ["GHL_ACCESS_TOKEN", "GHL_API_KEY"]:
        monkeypatch.delenv(k, raising=False)
    with pytest.raises(GHLAuthError):
        GHLClient.from_env(dotenv_path="/nonexistent")
