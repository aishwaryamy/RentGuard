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
| Phase 3: Agent + guardrails | Not started | LangGraph agent wrapping retrieval, with a guardrail layer against legal/causal claims and enforced citation. |
| Phase 4: Evaluation | Not started | Labeled address set, Precision@5/Recall@10/MRR scoring. |
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
  consideration for Phase 3, not a data error.

## Architecture

### Implemented through Phase 2

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
|-- agent/              # later: LangGraph agent + guardrails
|-- eval/                # later: eval harness
|-- app/                 # later: Streamlit UI
|-- data/
|   |-- bronze_hpd_violations.json
|   |-- bronze_311_housing_complaints.json
|   |-- silver_documents.json
|   `-- chroma_db/            # persisted vector store (gitignored if large)
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

## Local setup

```bash
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\Activate.ps1
pip install -r requirements.txt
cp .env.example .env
```

Edit `.env` to set your target ZIP codes and (optionally) your Socrata app
token.

## Run the pipeline

```bash
cd ingestion
python ingest_hpd_violations.py
python ingest_311_complaints.py

cd ../retrieval
python build_documents.py
python build_vector_store.py
python query.py    # interactive retrieval test
```

## MVP assumptions and exclusions

- Address matching is best-effort text normalization, not authoritative
  BBL (building identifier) matching.
- The agent (once built) reports what HPD/311 records say; it does not
  verify current building conditions or provide legal advice — this is a
  visible disclaimer requirement for Phase 3, not just a code comment.
- Scoped to 3 Brooklyn ZIP codes and 2023-present for the MVP — citywide,
  full-history coverage is a later item.
- No predictive risk scoring in the MVP.
- Multiple 311 complaints about the same building-wide condition on the
  same day are genuine, separate tenant reports, not duplicate data — see
  Phase 2 verified results above.

## Documentation

- [Two-week project plan](docs/NYC_Apartment_Safety_Assistant_2Week_Plan.md)
