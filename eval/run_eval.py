"""
Phase 4, step 2: score retrieval quality against the labeled query set
using Precision@5, Recall@10, and MRR — plus a max-possible-recall column,
since Recall@10 is mathematically capped whenever more than 10 relevant
documents exist for a query.

Usage:
    python run_eval.py
"""

import json
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

from retrieval.query import retrieve

PROJECT_ROOT = Path(__file__).resolve().parent.parent
LABELS_PATH = PROJECT_ROOT / "eval" / "labeled_queries.json"
REPORT_PATH = PROJECT_ROOT / "eval" / "eval_results.md"

TOP_K = 10


def precision_at_k(retrieved_ids: list[str], relevant_ids: set[str], k: int) -> float:
    top_k = retrieved_ids[:k]
    if not top_k:
        return 0.0
    hits = sum(1 for doc_id in top_k if doc_id in relevant_ids)
    return hits / len(top_k)


def recall_at_k(retrieved_ids: list[str], relevant_ids: set[str], k: int) -> float:
    if not relevant_ids:
        return 0.0
    top_k = retrieved_ids[:k]
    hits = sum(1 for doc_id in top_k if doc_id in relevant_ids)
    return hits / len(relevant_ids)


def mrr(retrieved_ids: list[str], relevant_ids: set[str]) -> float:
    for rank, doc_id in enumerate(retrieved_ids, start=1):
        if doc_id in relevant_ids:
            return 1.0 / rank
    return 0.0


def main():
    labeled_queries = json.load(open(LABELS_PATH))

    rows = []
    for item in labeled_queries:
        query = item["query"]
        zip_code = item["zip_code"]
        relevant_ids = set(item["relevant_ids"])

        if not relevant_ids:
            print(f"Skipping '{query}' — no relevant docs in ground truth")
            continue

        hits = retrieve(query, zip_code=zip_code, top_k=TOP_K)
        retrieved_ids = [h["id"] for h in hits]

        p5 = precision_at_k(retrieved_ids, relevant_ids, 5)
        r10 = recall_at_k(retrieved_ids, relevant_ids, TOP_K)
        max_possible_r10 = min(1.0, TOP_K / len(relevant_ids))
        rr = mrr(retrieved_ids, relevant_ids)

        rows.append({
            "query": query,
            "zip_code": zip_code,
            "num_relevant": len(relevant_ids),
            "precision_at_5": round(p5, 3),
            "recall_at_10": round(r10, 3),
            "max_possible_recall_at_10": round(max_possible_r10, 3),
            "mrr": round(rr, 3),
        })
        print(
            f"'{query}': P@5={p5:.3f}  R@10={r10:.3f} "
            f"(max possible={max_possible_r10:.3f})  MRR={rr:.3f}"
        )

    avg_p5 = sum(r["precision_at_5"] for r in rows) / len(rows)
    avg_r10 = sum(r["recall_at_10"] for r in rows) / len(rows)
    avg_max_r10 = sum(r["max_possible_recall_at_10"] for r in rows) / len(rows)
    avg_mrr = sum(r["mrr"] for r in rows) / len(rows)

    print(f"\nAverages across {len(rows)} queries:")
    print(f"  Precision@5: {avg_p5:.3f}")
    print(f"  Recall@10:   {avg_r10:.3f}  (avg max possible: {avg_max_r10:.3f})")
    print(f"  MRR:         {avg_mrr:.3f}")

    with open(REPORT_PATH, "w") as f:
        f.write("# Retrieval Evaluation Results\n\n")
        f.write(f"Evaluated {len(rows)} labeled queries against the ChromaDB retrieval layer.\n\n")
        f.write(
            "Note: Recall@10 is mathematically capped by how many relevant "
            "documents exist versus the fixed top-10 retrieval window — see "
            "the Max Possible R@10 column. A query with 294 relevant "
            "documents can never exceed 10/294 ≈ 0.034 recall even with "
            "perfect retrieval, so compare Recall@10 to its own ceiling, "
            "not to 1.0.\n\n"
        )
        f.write("| Query | ZIP | # Relevant | Precision@5 | Recall@10 | Max Possible R@10 | MRR |\n")
        f.write("|---|---|---|---|---|---|---|\n")
        for r in rows:
            f.write(
                f"| {r['query']} | {r['zip_code'] or '-'} | {r['num_relevant']} | "
                f"{r['precision_at_5']} | {r['recall_at_10']} | "
                f"{r['max_possible_recall_at_10']} | {r['mrr']} |\n"
            )
        f.write(
            f"\n**Averages:** Precision@5 = {avg_p5:.3f}, "
            f"Recall@10 = {avg_r10:.3f} (avg ceiling {avg_max_r10:.3f}), "
            f"MRR = {avg_mrr:.3f}\n"
        )

    print(f"\nWrote report to {REPORT_PATH}")


if __name__ == "__main__":
    main()
