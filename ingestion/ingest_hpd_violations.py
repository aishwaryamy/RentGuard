"""
Pull HPD Housing Maintenance Code Violations for a set of NYC ZIP codes.

Dataset: wvxf-dwi5 (the same official record HPD publishes on data.cityofnewyork.us)

Usage:
    python -m ingestion.ingest_hpd_violations
"""

import json
import os
from pathlib import Path

from socrata_client import fetch_all

DATASET_ID = "wvxf-dwi5"

# Start with one or two neighborhoods you know well — don't try to pull all
# of NYC for the MVP. Edit this list to your target ZIP codes.
TARGET_ZIPS = os.environ.get("TARGET_ZIPS", "11201,11215,11217").split(",")

# Scope to recent violations by default — the full history goes back to 2012
# and is far more than an MVP needs. Override in .env if you want more/less.
SINCE_DATE = os.environ.get("HPD_SINCE_DATE", "2023-01-01")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_PATH = PROJECT_ROOT / "data" / "bronze_hpd_violations.json"


def main():
    zip_clause = ", ".join(f"'{z.strip()}'" for z in TARGET_ZIPS)
    where = f"zip IN ({zip_clause}) AND inspectiondate >= '{SINCE_DATE}'"

    print(f"Fetching HPD violations for ZIPs: {TARGET_ZIPS}")
    rows = fetch_all(
        dataset_id=DATASET_ID,
        where=where,
        order_by="violationid",
        max_rows=int(os.environ.get("MAX_ROWS", "0")) or None,
    )

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "w") as f:
        json.dump(rows, f, indent=2)

    print(f"Wrote {len(rows)} HPD violation rows to {OUTPUT_PATH}")

    if rows:
        print("\nSample record fields:", list(rows[0].keys()))


if __name__ == "__main__":
    main()
