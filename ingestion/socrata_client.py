"""
Minimal client for NYC Open Data's Socrata (SODA) API.

No API key is required for light use, but requests get rate-limited faster
without one. Get a free app token at https://data.cityofnewyork.us/profile/app_tokens
and set SOCRATA_APP_TOKEN in your .env to raise the limit.
"""

import os
import time
import requests
from dotenv import load_dotenv

# Look for .env in the project root (one level up from this file's folder),
# regardless of which directory the script is actually run from.
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(_ROOT, ".env"))

BASE_URL = "https://data.cityofnewyork.us/resource/{dataset_id}.json"
PAGE_SIZE = 1000


def fetch_all(dataset_id: str, where: str, order_by: str, max_rows: int | None = None) -> list[dict]:
    """
    Page through a Socrata dataset with a $where filter.

    dataset_id: the Socrata 4x4 id, e.g. "wvxf-dwi5" for HPD violations.
    where: a SoQL $where clause, e.g. "zip = '11201'"
    order_by: column to order by for stable pagination, e.g. "violationid"
    max_rows: stop early after this many rows (useful while testing).
    """
    token = os.environ.get("SOCRATA_APP_TOKEN")
    headers = {"X-App-Token": token} if token else {}

    url = BASE_URL.format(dataset_id=dataset_id)
    rows: list[dict] = []
    offset = 0

    while True:
        params = {
            "$where": where,
            "$order": order_by,
            "$limit": PAGE_SIZE,
            "$offset": offset,
        }

        for attempt in range(1, 4):
            try:
                resp = requests.get(url, params=params, headers=headers, timeout=60)
                resp.raise_for_status()
                page = resp.json()
                break
            except (requests.exceptions.ReadTimeout, requests.exceptions.ConnectionError) as e:
                if attempt == 3:
                    raise
                wait = 2 ** attempt
                print(f"  request timed out (attempt {attempt}/3), retrying in {wait}s...")
                time.sleep(wait)

        if not page:
            break

        rows.extend(page)
        offset += PAGE_SIZE

        print(f"  fetched {len(rows)} rows so far...")

        if max_rows and len(rows) >= max_rows:
            rows = rows[:max_rows]
            break

        if len(page) < PAGE_SIZE:
            break

        time.sleep(0.2)  # be polite to the API

    return rows