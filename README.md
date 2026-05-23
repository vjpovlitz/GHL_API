# GHL_API

Python client for the [GoHighLevel](https://highlevel.stoplight.io/) (LeadConnector) API.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env  # then fill in credentials
```

## Layout

```
src/ghl_api/
  client.py        HTTP client + base request handling
  auth.py          OAuth token + refresh
  exceptions.py    Typed errors
  resources/       One module per API resource (contacts, opportunities, etc.)
tests/             pytest suite
```

## Usage

```python
from ghl_api import GHLClient

client = GHLClient.from_env()
contact = client.contacts.get("contact_id")
```

## API reference

- v2 (OAuth): https://services.leadconnectorhq.com — pinned via `Version` header
- v1 (legacy API key): https://rest.gohighlevel.com
