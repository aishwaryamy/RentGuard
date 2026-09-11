"""
Pull NYC 311 Service Requests filtered to HPD-agency housing complaints for
a set of ZIP codes.

Dataset: erm2-nwe9 (same dataset your friend's SafeEats project uses, filtered
to a different complaint slice: housing habitability rather than food safety).

Usage:
    python -m ingestion.ingest_311_complaints
"""

import json
import os
from pathlib import Path

from socrata_client import fetch_all

DATASET_ID = "erm2-nwe9"

TARGET_ZIPS = os.environ.get("TARGET_ZIPS", "11201,11215,11217").split(",")

# HPD-relevant complaint types. Check the dataset's `complaint_type` values
# yourself and adjust — NYC occasionally renames categories.
HOUSING_COMPLAINT_TYPES = [
    "HEAT/HOT WATER",
    "UNSANITARY CONDITION",
    "PLUMBING",
    "PAINT/PLASTER",
    "GENERAL CONSTRUCTION",
    "DOOR/WINDOW",
]

SINCE_DATE = os.environ.get("COMPLAINT_311_SINCE_DATE", "2023-01-01")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_PATH = PROJECT_ROOT / "data" / "bronze_311_housing_complaints.json"


def main():
    zip_clause = ", ".join(f"'{z.strip()}'" for z in TARGET_ZIPS)
    type_clause = ", ".join(f"'{t}'" for t in HOUSING_COMPLAINT_TYPES)
    where = (
        f"incident_zip IN ({zip_clause}) AND complaint_type IN ({type_clause}) "
        f"AND created_date >= '{SINCE_DATE}'"
    )

    print(f"Fetching 311 housing complaints for ZIPs: {TARGET_ZIPS}")
    rows = fetch_all(
        dataset_id=DATASET_ID,
        where=where,
        order_by="unique_key",
        max_rows=int(os.environ.get("MAX_ROWS", "0")) or None,
    )

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "w") as f:
        json.dump(rows, f, indent=2)

    print(f"Wrote {len(rows)} 311 complaint rows to {OUTPUT_PATH}")

    if rows:
        print("\nSample record fields:", list(rows[0].keys()))


if __name__ == "__main__":
    main()
