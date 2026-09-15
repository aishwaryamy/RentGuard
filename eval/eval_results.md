# Retrieval Evaluation Results

Evaluated 7 labeled queries against the ChromaDB retrieval layer.

Note: Recall@10 is mathematically capped by how many relevant documents exist versus the fixed top-10 retrieval window — see the Max Possible R@10 column. A query with 294 relevant documents can never exceed 10/294 ≈ 0.034 recall even with perfect retrieval, so compare Recall@10 to its own ceiling, not to 1.0.

| Query | ZIP | # Relevant | Precision@5 | Recall@10 | Max Possible R@10 | MRR |
|---|---|---|---|---|---|---|
| heat and hot water complaints | - | 294 | 1.0 | 0.034 | 0.034 | 1.0 |
| heat complaints | 11215 | 173 | 1.0 | 0.058 | 0.058 | 1.0 |
| unsanitary conditions in the apartment | - | 77 | 1.0 | 0.104 | 0.13 | 1.0 |
| plumbing problems | - | 59 | 1.0 | 0.169 | 0.169 | 1.0 |
| door or window complaints | - | 40 | 1.0 | 0.25 | 0.25 | 1.0 |
| paint or plaster complaints | - | 30 | 1.0 | 0.333 | 0.333 | 1.0 |
| smoke detector violations | - | 29 | 1.0 | 0.276 | 0.345 | 1.0 |

**Averages:** Precision@5 = 1.000, Recall@10 = 0.175 (avg ceiling 0.188), MRR = 1.000

## Note on near-misses

For "unsanitary conditions" and "smoke detector violations," 2 of the top-10
results in each case were HPD violations semantically related to the query
but excluded from ground truth (which was scoped to one record type per
query for label simplicity). This isn't a retrieval failure — the embedding
model correctly identified conceptually related content across record
types. It reflects a ground-truth labeling choice (type-scoped relevance)
rather than a retrieval quality gap, and is worth revisiting if the product
goal shifts toward "everything related to X" rather than "the specific
record type for X."
