"""
Phase 4, step 1: build a labeled evaluation set.

Rather than manually eyeballing which records are "correct" for each query,
we derive ground truth from structured metadata we already trust — e.g. for
the query "heat complaints," every document with complaint_type ==
"HEAT/HOT WATER" is relevant by definition. This is a standard, defensible
way to build an eval set without hand-labeling from scratch.

Usage:
    python build_labels.py
"""

import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DOCUMENTS_PATH = PROJECT_ROOT / "data" / "silver_documents.json"
OUTPUT_PATH = PROJECT_ROOT / "eval" / "labeled_queries.json"

# Each spec: a natural-language query, an optional ZIP scope, and the
# metadata condition that defines "relevant" ground truth for that query.
LABEL_SPECS = [
    {
        "query": "heat and hot water complaints",
        "zip_code": None,
        "match": {"source": "311_complaint", "complaint_type": "HEAT/HOT WATER"},
    },
    {
        "query": "heat complaints",
        "zip_code": "11215",
        "match": {"source": "311_complaint", "complaint_type": "HEAT/HOT WATER", "zip": "11215"},
    },
    {
        "query": "unsanitary conditions in the apartment",
        "zip_code": None,
        "match": {"source": "311_complaint", "complaint_type": "UNSANITARY CONDITION"},
    },
    {
        "query": "plumbing problems",
        "zip_code": None,
        "match": {"source": "311_complaint", "complaint_type": "PLUMBING"},
    },
    {
        "query": "door or window complaints",
        "zip_code": None,
        "match": {"source": "311_complaint", "complaint_type": "DOOR/WINDOW"},
    },
    {
        "query": "paint or plaster complaints",
        "zip_code": None,
        "match": {"source": "311_complaint", "complaint_type": "PAINT/PLASTER"},
    },
    {
        "query": "smoke detector violations",
        "zip_code": None,
        "match": {"source": "hpd_violation", "keyword": "SMOKE DETECTOR"},
    },
]


def matches(doc: dict, condition: dict) -> bool:
    meta = doc["metadata"]
    for key, value in condition.items():
        if key == "keyword":
            if value.upper() not in doc["text"].upper():
                return False
        elif meta.get(key) != value:
            return False
    return True


def main():
    documents = json.load(open(DOCUMENTS_PATH))

    labeled = []
    for spec in LABEL_SPECS:
        relevant_ids = [d["id"] for d in documents if matches(d, spec["match"])]
        labeled.append({
            "query": spec["query"],
            "zip_code": spec["zip_code"],
            "relevant_ids": relevant_ids,
        })
        print(f"'{spec['query']}' (zip={spec['zip_code']}): {len(relevant_ids)} relevant docs")

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "w") as f:
        json.dump(labeled, f, indent=2)

    print(f"\nWrote {len(labeled)} labeled queries to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
