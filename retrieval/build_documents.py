"""
Phase 2, step 1: turn the raw Bronze JSON records into a flat list of
{id, text, metadata} documents ready for embedding.

Usage:
    python build_documents.py
"""

import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
HPD_PATH = PROJECT_ROOT / "data" / "bronze_hpd_violations.json"
COMPLAINTS_PATH = PROJECT_ROOT / "data" / "bronze_311_housing_complaints.json"
OUTPUT_PATH = PROJECT_ROOT / "data" / "silver_documents.json"


def hpd_record_to_document(row: dict) -> dict:
    address = f"{row.get('housenumber', '')} {row.get('streetname', '')}".strip()
    zip_code = row.get("zip", "unknown")
    violation_class = row.get("class", "unknown")
    inspection_date = row.get("inspectiondate", "unknown date")[:10]
    description = row.get("novdescription", "No description available.")
    status = row.get("currentstatus", "unknown status")

    text = (
        f"HPD housing violation at {address}, ZIP {zip_code}. "
        f"Class {violation_class} violation, inspected {inspection_date}. "
        f"Description: {description} "
        f"Current status: {status}."
    )

    return {
        "id": f"hpd_{row.get('violationid')}",
        "text": text,
        "metadata": {
            "source": "hpd_violation",
            "address": address,
            "zip": zip_code,
            "violation_class": violation_class,
            "date": inspection_date,
            "status": status,
        },
    }


def complaint_record_to_document(row: dict) -> dict:
    address = row.get("incident_address", "unknown address")
    zip_code = row.get("incident_zip", "unknown")
    complaint_type = row.get("complaint_type", "unknown type")
    descriptor = row.get("descriptor", "")
    descriptor_2 = row.get("descriptor_2", "")
    created_date = row.get("created_date", "unknown date")[:10]
    status = row.get("status", "unknown status")
    resolution = row.get("resolution_description", "No resolution recorded.")

    text = (
        f"311 housing complaint at {address}, ZIP {zip_code}. "
        f"Type: {complaint_type}"
        + (f" - {descriptor}" if descriptor else "")
        + (f" ({descriptor_2})" if descriptor_2 else "")
        + f". Reported {created_date}. Status: {status}. "
        f"Resolution: {resolution}"
    )

    return {
        "id": f"complaint_{row.get('unique_key')}",
        "text": text,
        "metadata": {
            "source": "311_complaint",
            "address": address,
            "zip": zip_code,
            "complaint_type": complaint_type,
            "date": created_date,
            "status": status,
        },
    }


def main():
    hpd_rows = json.load(open(HPD_PATH))
    complaint_rows = json.load(open(COMPLAINTS_PATH))

    documents = [hpd_record_to_document(r) for r in hpd_rows]
    documents += [complaint_record_to_document(r) for r in complaint_rows]

    with open(OUTPUT_PATH, "w") as f:
        json.dump(documents, f, indent=2)

    print(f"Built {len(documents)} documents ({len(hpd_rows)} HPD + {len(complaint_rows)} 311)")
    print(f"Wrote to {OUTPUT_PATH}")
    print("\nSample document:")
    print(json.dumps(documents[0], indent=2))


if __name__ == "__main__":
    main()
