"""
Address verification against the US Census Bureau's free public geocoder —
no API key required. Used to distinguish "this isn't a real address" from
"this is real, we just have no records for it."
"""

import requests

CENSUS_GEOCODER_URL = "https://geocoding.geo.census.gov/geocoder/locations/onelineaddress"


def verify_address(address_text: str) -> dict:
    """
    Returns one of:
      {"status": "found", "matched_address": str, "zip": str}
      {"status": "not_found"}
      {"status": "unknown"}   # geocoder itself failed/timed out — don't claim either way
    """
    try:
        resp = requests.get(
            CENSUS_GEOCODER_URL,
            params={"address": address_text, "benchmark": "Public_AR_Current", "format": "json"},
            timeout=6,
        )
        resp.raise_for_status()
        data = resp.json()
        matches = data.get("result", {}).get("addressMatches", [])
        if not matches:
            return {"status": "not_found"}
        match = matches[0]
        return {
            "status": "found",
            "matched_address": match.get("matchedAddress"),
            "zip": match.get("addressComponents", {}).get("zip"),
        }
    except Exception:
        return {"status": "unknown"}
