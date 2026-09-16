# RentGuard (NYC Apartment Safety Assistant)

RentGuard is an AI-native platform that helps NYC renters research a
building's safety and habitability history before signing a lease, combining
NYC HPD housing violations and 311 housing complaints with a
retrieval-augmented, guardrailed conversational agent.

Unlike a keyword search tool, RentGuard answers natural-language questions
— *"has this building had heat complaints in the past year?"* — grounded
strictly in real city records, with citations and a refusal to make legal
or causal claims.

## Project goals

The MVP is designed to help users:

1. Look up any NYC address's HPD violation history (Class A/B/C, open vs.
   closed) and recent 311 housing complaints.
2. Ask natural-language safety questions and get answers grounded in
   retrieved city records, with citations.
3. Trust that the agent won't make legal/causal claims — it reports what
   HPD/311 records say, not legal conclusions.
4. See a measurable evaluation of retrieval quality (Precision@k, Recall@k,
   MRR), not just an unverified demo.

## Current status

| Phase | Status | Result |
|---|---|---|
| Phase 1: Data ingestion | Complete | HPD violations and 311 housing complaints pulled from NYC Open Data via the Socrata API for 3 Brooklyn ZIP codes (11201, 11215, 11217), scoped to 2023-present. |
| Phase 2: Retrieval (RAG) | Complete | Records chunked into embeddable text, embedded locally (sentence-transformers, all-MiniLM-L6-v2), indexed in ChromaDB, and retrievable via combined semantic search + structured metadata filtering. |
| Phase 3: Agent + guardrails | Complete | LangGraph agent (retrieve → generate → guardrail → retry-or-fallback) built with OpenAI's gpt-4o-mini, enforcing citation and blocking legal/causal claims. |
| Phase 4: Evaluation | Complete | Retrieval scored against 7 metadata-derived ground-truth queries: Precision@5 = 1.000, MRR = 1.000, Recall@10 = 0.175 (average ceiling 0.188 — most queries hit their max-possible recall exactly). |
| Phase 5: UI + docs | Not started | Streamlit chat interface, final documentation pass. |

Verified Phase 1 results:

- 500 HPD violation rows pulled for ZIPs 11201/11215/11217, inspected
  2023-01-01 or later.
- 500 311 housing complaint rows (Heat/Hot Water, Unsanitary Condition,
  Plumbing, Paint/Plaster, General Construction, Door/Window), same ZIPs
  and date range.
- Ingestion is retry-safe: transient API timeouts are retried up to 3 times
  with exponential backoff before failing.
- `.env`-driven configuration (ZIP codes, row caps, date filters) verified
  to actually take effect after fixing a missing `load_dotenv()` call.

Verified Phase 2 results:

- 1,000 documents built (500 HPD + 500 311), each with normalized text and
  structured metadata (address, ZIP, violation class/complaint type, date,
  status).
- All 1,000 documents embedded locally (no external API calls or cost) and
  indexed into a persistent ChromaDB collection.
- Retrieval correctness manually verified with three test queries:
  - ZIP-filtered semantic search returned only records within the
    specified ZIP, with topically correct results (heat complaints for a
    "heat complaints" query).
  - Unfiltered semantic search correctly distinguished record *type*
    (surfacing HPD violations, not 311 complaints, for a "smoke detector"
    query) across multiple ZIP codes.
  - Changing the ZIP filter changed the result set entirely, confirming the
    structured filter is genuinely applied, not decorative.
- Discovered and documented a real data-quality nuance: multiple distinct
  311 complaints (different `unique_key`s) can describe the same
  building-wide condition on the same day — a dedup-for-display
  consideration for later phases, not a data error.

Verified Phase 3 results:

- LangGraph agent implemented with 5 nodes: retrieve, generate, guardrail
  check, regenerate (retry), and safe fallback.
- Two independent guardrail checks verified working: a citation check
  (does the answer reference actual dates/classes/types from the retrieved
  records?) and a legal-claim check (does the answer use language like
  "illegal," "liable," "breaking the law"?).
- Observed the full retry→fallback path in practice: a broad, unfiltered
  query produced an answer that failed the citation check twice in a row,
  and the agent correctly fell back to showing raw source records rather
  than presenting an ungrounded answer.
- Observed the legal-claim guardrail's target behavior directly: asked
  "is my landlord breaking the law?", the agent reported only what the
  records show ("do not support a claim regarding any legal issues") with
  no legal conclusion — the desired outcome, achieved via the system
  prompt without needing the retry path.
- LLM backend: OpenAI (`gpt-4o-mini`), swapped in from an initial
  Anthropic implementation due to API credit availability during
  development — the `agent/llm.py` module is a thin wrapper, so swapping
  providers again later is a small, contained change.

Verified Phase 4 results:

- Built a labeled evaluation set of 7 queries by deriving ground truth from
  existing metadata (e.g., every document with `complaint_type ==
  "HEAT/HOT WATER"` is relevant to a "heat complaints" query) rather than
  hand-labeling from scratch.
- **Precision@5 = 1.000 and MRR = 1.000 across all 7 queries** — every
  top-5 result was relevant, and the first result was always relevant.
- Recall@10 averaged 0.175, but this number alone is misleading: it's
  mathematically capped by how many relevant documents exist versus a
  fixed top-10 window. Added a "max possible recall" column to the eval
  report — 5 of 7 queries hit their ceiling exactly, meaning retrieval
  found every relevant document it possibly could within the top 10.
- Investigated the 2 queries that fell short of their ceiling and found a
  genuine, explainable edge case: HPD violations semantically related to
  the query (e.g., mold/pest language in a violation description) were
  retrieved ahead of some in-scope 311 complaints. This reflects a
  ground-truth labeling choice (relevance scoped to one record type per
  query), not a retrieval defect — documented in `eval/eval_results.md`.

## Architecture

### Implemented through Phase 4

```text
NYC Open Data
  |-- HPD Housing Maintenance Code Violations (dataset wvxf-dwi5)
  `-- NYC 311 Service Requests (dataset erm2-nwe9), filtered to
      HPD-agency housing complaints
       |
       v
  Python ingestion (Socrata API, paginated, retry-safe)
       |
       v
  Bronze layer: normalized JSON (data/bronze_*.json)
       |
       v
  Chunking (build_documents.py): structured rows -> natural-language
  text + metadata (Silver layer: data/silver_documents.json)
       |
       v
  Local embedding (sentence-transformers, all-MiniLM-L6-v2)
       |
       v
  ChromaDB persistent vector store (data/chroma_db/)
       |
       v
  Retrieval function: semantic search + structured metadata filter
  (retrieval/query.py)
       |
       v
  LangGraph agent (agent/graph.py): retrieve -> generate -> guardrail
  check -> retry once if flagged -> done, or fall back to raw records
       |
       v
  Evaluation harness (eval/): metadata-derived ground truth,
  Precision@5 / Recall@10 / MRR scoring with ceiling analysis
```

### Planned end-to-end platform

```text
NYC Open Data
   -> Bronze JSON
   -> Silver documents (chunked + embedded)
   -> ChromaDB vector store
   -> LangGraph agent (retrieval tool + guardrails + response generator)
   -> Evaluation harness (Precision@k / Recall@k / MRR)
   -> Streamlit chat UI
```

## Data sources

| Source | Dataset ID | Selection | Notes |
|---|---|---|---|
| HPD Housing Maintenance Code Violations | `wvxf-dwi5` | Class A/B/C/I violations, 2023-present, 3 ZIP codes | Same official record HPD itself publishes; updated daily |
| NYC 311 Service Requests | `erm2-nwe9` | Filtered to Heat/Hot Water, Unsanitary Condition, Plumbing, Paint/Plaster, General Construction, Door/Window | Same underlying dataset as SafeEats, filtered to a different complaint slice |

## Repository structure

```text
nyc-apartment-safety-assistant/
|-- ingestion/
|   |-- socrata_client.py     # paginated, retry-safe Socrata API client
|   |-- ingest_hpd_violations.py
|   `-- ingest_311_complaints.py
|-- retrieval/
|   |-- build_documents.py    # Bronze JSON -> chunked text + metadata
|   |-- build_vector_store.py # embed + index into ChromaDB
|   `-- query.py               # semantic + structured retrieval
|-- agent/
|   |-- prompts.py             # system prompt enforcing citation + no legal claims
|   |-- guardrails.py          # citation check + legal-claim check
|   |-- llm.py                 # thin LLM provider wrapper (currently OpenAI)
|   |-- graph.py               # LangGraph state machine
|   `-- run.py                  # interactive CLI
|-- eval/                       # retrieval evaluation: labeled queries, Precision/Recall/MRR scoring
|   |-- build_labels.py
|   |-- run_eval.py
|   |-- labeled_queries.json
|   `-- eval_results.md
|-- app/                 # later: Streamlit UI
|-- data/
|   |-- bronze_hpd_violations.json
|   |-- bronze_311_housing_complaints.json
|   |-- silver_documents.json
|   `-- chroma_db/            # persisted vector store
|-- docs/
|-- tests/
|-- requirements.txt
|-- .env.example
`-- README.md
```

## Prerequisites

- Python 3.10+ (3.11 or 3.13 recommended)
- A free NYC Open Data account is optional but recommended: get an app
  token at https://data.cityofnewyork.us/profile/app_tokens for higher
  rate limits.
- An OpenAI API key with available credits (for the agent's generation
  step).

## Local setup

```bash
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\Activate.ps1
pip install -r requirements.txt
cp .env.example .env
```

Edit `.env` to set your target ZIP codes, your OpenAI API key, and
(optionally) your Socrata app token.

## Run the pipeline

```bash
cd ingestion
python ingest_hpd_violations.py
python ingest_311_complaints.py

cd ../retrieval
python build_documents.py
python build_vector_store.py
python query.py    # interactive retrieval test

cd ..
python -m agent.run    # interactive agent chat, run from project root

cd eval
python build_labels.py
python run_eval.py
```

## MVP assumptions and exclusions

- Address matching is best-effort text normalization, not authoritative
  BBL (building identifier) matching.
- The agent reports what HPD/311 records say; it does not verify current
  building conditions or provide legal advice — this is a visible
  disclaimer requirement for the Phase 5 UI, not just a code comment.
- Scoped to 3 Brooklyn ZIP codes and 2023-present for the MVP — citywide,
  full-history coverage is a later item.
- No predictive risk scoring in the MVP.
- Multiple 311 complaints about the same building-wide condition on the
  same day are genuine, separate tenant reports, not duplicate data — see
  Phase 2 verified results above.
- Guardrails use explainable keyword/pattern matching for the legal-claim
  check, not a second LLM call as judge — a deliberate simplicity/cost
  tradeoff for the MVP, worth naming as a "if I had more time" improvement.
- Small sample size (500 rows per source) means some complaint categories
  (e.g., General Construction) may be underrepresented or absent entirely
  in the current dataset.

## Documentation

- [Two-week project plan](docs/NYC_Apartment_Safety_Assistant_2Week_Plan.md)
- [Retrieval evaluation results](eval/eval_results.md)
