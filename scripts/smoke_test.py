"""Smoke test: verify the access token in .env can talk to GHL.

Tries a few low-risk read endpoints and prints what the API returns,
so we can identify what kind of token it is and what scope it has.
"""
from __future__ import annotations

import os
import sys

import httpx
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("GHL_ACCESS_TOKEN", "").strip()
VERSION = os.getenv("GHL_API_VERSION", "2021-07-28")
LOCATION_ID = os.getenv("GHL_LOCATION_ID", "").strip()

if not TOKEN:
    print("ERROR: GHL_ACCESS_TOKEN is empty in .env")
    sys.exit(1)

BASE = "https://services.leadconnectorhq.com"
HEADERS = {
    "Authorization": f"Bearer {TOKEN}",
    "Accept": "application/json",
    "Version": VERSION,
}


def show(label: str, resp: httpx.Response) -> None:
    print(f"\n--- {label}  [{resp.status_code} {resp.reason_phrase}] ---")
    body = resp.text
    print(body[:600] + ("..." if len(body) > 600 else ""))


def main() -> None:
    print(f"Token length: {len(TOKEN)} chars")
    print(f"Token prefix: {TOKEN[:6]}...  (redacted)")
    print(f"Version header: {VERSION}")
    print(f"Location ID:  {LOCATION_ID or '(not set)'}")

    with httpx.Client(timeout=15.0, headers=HEADERS) as c:
        show("GET /oauth/installedLocations", c.get(f"{BASE}/oauth/installedLocations"))
        show("GET /locations/search", c.get(f"{BASE}/locations/search"))
        if LOCATION_ID:
            show(
                f"GET /locations/{LOCATION_ID}",
                c.get(f"{BASE}/locations/{LOCATION_ID}"),
            )
            show(
                "GET /contacts/  (1 result)",
                c.get(
                    f"{BASE}/contacts/",
                    params={"locationId": LOCATION_ID, "limit": 1},
                ),
            )


if __name__ == "__main__":
    main()
