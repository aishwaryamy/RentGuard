"""
Live building lookups against NYC's free public APIs (no key required):

1. NYC Planning Labs Geosearch -> resolves a typed address to a BBL (the
   city's tax-lot ID), plus coordinates and neighborhood.
2. NYC Open Data (Socrata) -> HPD violations and HPD-routed 311 complaints,
   filtered by that BBL.
"""

from __future__ import annotations

import os
import re
import time
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone

import requests

GEOSEARCH_URL = "https://geosearch.planninglabs.nyc/v2/search"
SOCRATA_URL = "https://data.cityofnewyork.us/resource/{dataset}.json"
HPD_VIOLATIONS = "wvxf-dwi5"
SERVICE_REQUESTS_311 = "erm2-nwe9"
ROW_LIMIT = 5000
TIMEOUT = 25


class LookupFailed(Exception):
    """A live city API could not be reached or returned unusable data."""


def _get_json(url: str, params: dict | None = None, retries: int = 2):
    headers = {}
    token = os.environ.get("SOCRATA_APP_TOKEN")
    if token and "data.cityofnewyork.us" in url:
        headers["X-App-Token"] = token

    last_error = None
    for attempt in range(retries + 1):
        try:
            resp = requests.get(url, params=params, headers=headers, timeout=TIMEOUT)
            resp.raise_for_status()
            return resp.json()
        except (requests.RequestException, ValueError) as exc:
            last_error = exc
            if attempt < retries:
                time.sleep(1.5 * (attempt + 1))
    raise LookupFailed(f"Could not reach {url.split('/')[2]}: {last_error}")


def _check_bbl(bbl: str) -> None:
    # BBL goes into a query string, so only ever allow exactly 10 digits.
    if not re.fullmatch(r"\d{10}", str(bbl)):
        raise LookupFailed(f"Invalid BBL: {bbl!r}")


def _clean(text: str | None) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


# ---------------------------------------------------------------- geocoding

def search_addresses(text: str, size: int = 5) -> list[dict]:
    """Resolve typed text to candidate NYC buildings (each has a BBL)."""
    text = (text or "").strip()
    if len(text) < 3:
        return []

    data = _get_json(GEOSEARCH_URL, {"text": text, "size": size})

    results, seen = [], set()
    for feat in data.get("features", []):
        props = feat.get("properties", {})
        pad = (props.get("addendum") or {}).get("pad") or {}
        bbl = pad.get("bbl")
        if not bbl or not re.fullmatch(r"\d{10}", str(bbl)):
            continue  # streets, neighborhoods, etc. have no tax lot

        label = props.get("label") or props.get("name") or ""
        key = (str(bbl), label)
        if key in seen:
            continue
        seen.add(key)

        coords = (feat.get("geometry") or {}).get("coordinates") or [None, None]
        results.append({
            "label": label,
            "name": props.get("name") or label.split(",")[0],
            "bbl": str(bbl),
            "bin": pad.get("bin"),
            "borough": props.get("borough"),
            "neighborhood": props.get("neighbourhood"),
            "zip": props.get("postalcode"),
            "lat": coords[1],
            "lon": coords[0],
        })
    return results


# ---------------------------------------------------------------- city data

def fetch_violations(bbl: str) -> list[dict]:
    _check_bbl(bbl)
    rows = _get_json(SOCRATA_URL.format(dataset=HPD_VIOLATIONS), {
        "$where": f"bbl='{bbl}'",
        "$order": "inspectiondate DESC",
        "$limit": ROW_LIMIT,
    })
    out = []
    for r in rows:
        status_raw = (r.get("violationstatus") or "").lower()
        out.append({
            "id": r.get("violationid"),
            "class": (r.get("class") or "?").upper(),
            "date": (r.get("inspectiondate") or "")[:10],
            "status": "Open" if status_raw.startswith("open") else "Closed",
            "status_detail": _clean(r.get("currentstatus")),
            "description": _clean(r.get("novdescription")),
            "rent_impairing": r.get("rentimpairing") == "Y",
        })
    return out


def fetch_complaints(bbl: str) -> list[dict]:
    _check_bbl(bbl)
    rows = _get_json(SOCRATA_URL.format(dataset=SERVICE_REQUESTS_311), {
        "$where": f"bbl='{bbl}' AND agency='HPD'",
        "$order": "created_date DESC",
        "$limit": ROW_LIMIT,
    })
    out = []
    for r in rows:
        detail = " - ".join(p for p in (r.get("descriptor"), r.get("descriptor_2")) if p)
        out.append({
            "id": r.get("unique_key"),
            "date": (r.get("created_date") or "")[:10],
            "type": _clean(r.get("complaint_type")),
            "detail": _clean(detail),
            "status": _clean(r.get("status")),
        })
    return out


# ---------------------------------------------------------------- summary

def compute_stats(violations: list[dict], complaints: list[dict]) -> dict:
    today = date.today()
    d12 = (today - timedelta(days=365)).isoformat()
    d36 = (today - timedelta(days=3 * 365)).isoformat()

    open_v = [v for v in violations if v["status"] == "Open"]
    per_year: dict[str, Counter] = defaultdict(Counter)
    for v in violations:
        if v["date"]:
            per_year[v["date"][:4]][v["class"]] += 1

    dates = sorted(v["date"] for v in violations if v["date"])
    open_dates = sorted(v["date"] for v in open_v if v["date"])
    complaints_12m = [c for c in complaints if c["date"] >= d12]
    complaints_3y = [c for c in complaints if c["date"] >= d36]
    type_counts = Counter(c["type"] for c in complaints_3y if c["type"])

    return {
        "total": len(violations),
        "open": len(open_v),
        "closed": len(violations) - len(open_v),
        "by_class": dict(Counter(v["class"] for v in violations)),
        "open_by_class": dict(Counter(v["class"] for v in open_v)),
        "last_12m": sum(1 for v in violations if v["date"] >= d12),
        "last_3y": sum(1 for v in violations if v["date"] >= d36),
        "first_date": dates[0] if dates else None,
        "latest_date": dates[-1] if dates else None,
        "oldest_open_date": open_dates[0] if open_dates else None,
        "per_year": {y: dict(c) for y, c in per_year.items()},
        "complaints_total": len(complaints),
        "complaints_12m": len(complaints_12m),
        "complaints_3y": len(complaints_3y),
        "complaint_types_3y": dict(type_counts),
    }


def build_report(building: dict) -> dict:
    bbl = building["bbl"]
    violations = fetch_violations(bbl)
    complaints = fetch_complaints(bbl)
    return {
        "building": building,
        "violations": violations,
        "complaints": complaints,
        "stats": compute_stats(violations, complaints),
        "truncated": len(violations) >= ROW_LIMIT or len(complaints) >= ROW_LIMIT,
        "fetched_at": datetime.now(timezone.utc).isoformat(timespec="minutes"),
    }
