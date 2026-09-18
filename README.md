# RentGuard (NYC Apartment Safety Assistant)

RentGuard is an AI-native platform that helps NYC renters research a
building's safety and habitability history before signing a lease, combining
NYC HPD housing violations and 311 housing complaints with a
retrieval-augmented, guardrailed conversational agent.

Unlike a keyword search tool, RentGuard answers natural-language questions
— *"has this building had heat complaints in the past year?"* — grounded
strictly in real city records, with citations and a refusal to make legal
or causal claims.

**Live app:** [rentguard.streamlit.app](https://rentguard-fwpwhgu6y7iwhzbozcefml.streamlit.app/)

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
5. Actually be usable by real people — deployed, multi-neighborhood, with
   real address verification and session memory.

## Current status

| Phase | Status | Result |
|---|---|---|
| Phase 1: Data ingestion | Complete | HPD violations and 311 housing complaints pulled from NYC Open Data via the Socrata API across 12 neighborhoods spanning all 5 boroughs, 2023–present. |
| Phase 2: Retrieval (RAG) | Complete | Records chunked into embeddable text, embedded locally (sentence-transformers, all-MiniLM-L6-v2), indexed in ChromaDB, retrievable via combined semantic search + structured metadata filtering. |
| Phase 3: Agent + guardrails | Complete | LangGraph agent (retrieve → generate → guardrail → retry-or-fallback) built with OpenAI's gpt-4o-mini. |
| Phase 4: Evaluation | Complete | Retrieval scored against 7 metadata-derived ground-truth queries: Precision@5 = 1.000, MRR = 1.000, Recall@10 = 0.175 (average ceiling 0.188 — most queries hit their max-possible recall exactly). |
| Phase 5: Public deployment + hardening | Complete | Deployed to Streamlit Community Cloud with a multi-tab UI, session memory, real address verification, and 7 distinct bugs found and fixed through adversarial testing (below). |

Verified Phase 1 results:

- 500+ HPD violation rows and 500+ 311 complaint rows across 12 ZIP codes
  (Manhattan, Brooklyn, Queens, Bronx), inspected/reported 2023-01-01 or
  later.
- Ingestion is retry-safe: transient API timeouts are retried up to 3 times
  with exponential backoff before failing.
- `.env`-driven configuration verified to actually take effect after
  fixing a missing `load_dotenv()` call.

Verified Phase 2 results:

- Documents built from all ingested records, each with normalized text and
  structured metadata (address, ZIP, violation class/complaint type, date,
  status), embedded locally at zero API cost and indexed in ChromaDB.
- Retrieval correctness manually verified: ZIP-filtered semantic search
  returns only records in-scope; unfiltered search correctly distinguishes
  record type by meaning, not just keywords.

Verified Phase 3 results:

- LangGraph agent with 5 core nodes (retrieve, generate, guardrail,
  regenerate, safe fallback), enforcing citation and blocking legal/causal
  claims via a system prompt plus explainable pattern-based checks.
- Verified the full retry→fallback path firing correctly on an
  under-grounded answer, and the legal-claim guardrail correctly declining
  to make a legal determination on request.

Verified Phase 4 results:

- Precision@5 = 1.000 and MRR = 1.000 across all 7 labeled queries — every
  top-5 result relevant, first result always relevant.
- Recall@10 correctly interpreted against its own mathematical ceiling
  (capped by how many relevant documents exist vs. a fixed top-10 window)
  rather than compared naively to 1.0 — 5 of 7 queries hit their ceiling
  exactly.
- Investigated and explained the 2 queries that fell short: a genuine,
  documented cross-record-type semantic overlap, not a retrieval defect.

Verified Phase 5 results — public launch and adversarial testing:

- **Deployed** to Streamlit Community Cloud with a 5-tab interface (Chat,
  Coverage & Stats, Tenant Resources, Feedback & Updates, About),
  session-based rate limiting (5 questions/session), a locked dark theme
  for cross-browser legibility, and the dev toolbar hidden for a
  public-facing experience.
- **Coverage expanded** from 3 Brooklyn ZIPs to 12 neighborhoods across
  all 5 boroughs, with a real interactive map (actual complaint lat/lon,
  not decorative) and live complaint-type bar charts per neighborhood.
- **Shareable deep links**: asking a question updates the URL with the
  question and ZIP as query params, so any link can be copied and shared
  to reproduce that exact answer.
- **Real address verification** via the US Census Bureau's free public
  geocoding API — the agent can now distinguish "this address doesn't
  exist," "this is real but has no records," and "this is inside/outside
  our coverage area" instead of guessing.
- **Session memory**: the agent now tracks the last address/ZIP discussed
  in a session, so natural follow-ups ("what's near that address?") work
  without needing to repeat the full address every time.
- **7 distinct bugs found and fixed through deliberate adversarial
  testing** (asking edge-case and out-of-scope questions on purpose, not
  just happy-path testing):
  1. *Ambiguous reference hallucination* — asking about "this building"
     with no address given caused the model to silently pick an
     unrelated real record and answer as if it were the intended
     building. Fixed by detecting ambiguous references and asking for
     clarification instead of guessing.
  2. *Absolute safety-claim overreach* — asked to find buildings with "no
     issues," the model conflated "no violation was issued" with
     "confirmed zero complaints ever," which the dataset (a record of
     reported complaints only, not a full building registry) can't
     actually prove. Fixed with an explicit guardrail against absolute
     claims plus a system-prompt rule distinguishing "no reported issues"
     from "confirmed issue-free."
  3. *Out-of-scope location leakage* — a Jersey City, NJ address returned
     unrelated NYC violation records instead of being recognized as
     outside coverage. Fixed with explicit out-of-scope detection before
     the agent is even called.
  4. *Ungrounded fallback records* — when the guardrail correctly
     rejected an answer, the fallback path showed raw records without
     checking whether any of them actually matched the address asked
     about. Fixed by requiring an explicit address/street-number match
     before treating retrieved records as relevant.
  5. *Address hallucination* — asked a follow-up question with no address
     of its own, the model fabricated an entirely new, unrelated address
     in its summary sentence. Fixed with a guardrail comparing every
     address mentioned in an answer against the actual retrieved records'
     street numbers (matching by number rather than full formatted string,
     to tolerate abbreviation differences like "St" vs "Street").
  6. *Proximity-question misfire* — "what's near that address?" was
     incorrectly treated as "find this exact address," failing because no
     exact match existed. Fixed by detecting proximity language and
     switching to ZIP-scoped broad search instead of exact-address
     matching.
  7. *False-positive legal-claim blocking* — official HPD violation
     language legitimately uses words like "illegal" (e.g., "illegal
     fastening" as a code-violation category); the keyword guardrail
     flagged this as the model making its own legal claim. Fixed by
     checking whether the flagged language already appears in the source
     records (legitimate citation) versus being introduced by the model
     with no grounding (genuine overreach) — the same source-grounded
     comparison approach used for the address-hallucination fix.
- **Feedback and waitlist capture** built in (Feedback & Updates tab),
  with a documented limitation: local CSV storage can reset on Streamlit
  Cloud redeploys, so this is treated as pilot-stage, not
  production-durable, and is checked/downloaded periodically.

## Architecture

### Implemented through Phase 5

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
  Pre-agent scope checks (app/streamlit_app.py): ambiguous reference,
  out-of-scope location/ZIP, proximity-vs-exact-address detection
       |
       v
  LangGraph agent (agent/graph.py):
    retrieve -> generate (+ Census address verification) -> guardrail
    (source-grounded legal-claim, absolute-safety-claim, and address-
    hallucination checks) -> retry once if flagged -> done, or fall
    back to address-matched raw records
       |
       v
  Evaluation harness (eval/): metadata-derived ground truth,
  Precision@5 / Recall@10 / MRR scoring with ceiling analysis
       |
       v
  Streamlit UI (app/): 5-tab interface, session memory, shareable
  links, feedback/waitlist capture — deployed on Streamlit Community
  Cloud
```

## Data sources

| Source | Dataset ID | Selection | Notes |
|---|---|---|---|
| HPD Housing Maintenance Code Violations | `wvxf-dwi5` | Class A/B/C/I violations, 2023-present, 12 ZIP codes | Same official record HPD itself publishes; updated daily |
| NYC 311 Service Requests | `erm2-nwe9` | Filtered to Heat/Hot Water, Unsanitary Condition, Plumbing, Paint/Plaster, General Construction, Door/Window | Same underlying dataset as SafeEats, filtered to a different complaint slice |
| US Census Bureau Geocoder | — | Real-time address verification | Free, no API key required |

## Repository structure

```text
nyc-apartment-safety-assistant/
|-- .streamlit/
|   `-- config.toml          # locked theme, hidden dev toolbar
|-- ingestion/
|   |-- socrata_client.py     # paginated, retry-safe Socrata API client
|   |-- ingest_hpd_violations.py
|   `-- ingest_311_complaints.py
|-- retrieval/
|   |-- build_documents.py    # Bronze JSON -> chunked text + metadata
|   |-- build_vector_store.py # embed + index into ChromaDB
|   `-- query.py               # semantic + structured retrieval
|-- agent/
|   |-- prompts.py             # system prompt: citation, no legal/absolute claims, address grounding
|   |-- guardrails.py          # source-grounded legal-claim, safety-claim, address checks
|   |-- llm.py                 # thin LLM provider wrapper (OpenAI)
|   |-- geocode.py             # US Census address verification
|   |-- graph.py               # LangGraph state machine
|   `-- run.py                  # interactive CLI
|-- eval/                       # retrieval evaluation: labeled queries, Precision/Recall/MRR scoring
|   |-- build_labels.py
|   |-- run_eval.py
|   |-- labeled_queries.json
|   `-- eval_results.md
|-- app/
|   `-- streamlit_app.py       # 5-tab UI, session memory, shareable links, feedback capture
|-- data/
|   |-- bronze_hpd_violations.json
|   |-- bronze_311_housing_complaints.json
|   |-- silver_documents.json
|   |-- chroma_db/            # persisted vector store
|   |-- feedback.csv          # user feedback (gitignored, local/pilot storage)
|   `-- signups.csv           # waitlist signups (gitignored, local/pilot storage)
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
- An OpenAI API key with available credits.

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
python -m agent.run    # interactive agent chat (CLI), run from project root

cd eval
python build_labels.py
python run_eval.py

cd ..
streamlit run app/streamlit_app.py    # full web UI
```

## Deployment

Deployed on [Streamlit Community Cloud](https://share.streamlit.io),
connected directly to this repo's `main` branch, main file
`app/streamlit_app.py`. OpenAI API key is stored in Streamlit's encrypted
secrets manager, not committed to the repo. Auto-redeploys on push to
`main`.

## MVP assumptions and exclusions

- Address matching uses street-number comparison (tolerant of
  abbreviation differences) rather than authoritative BBL (building
  identifier) matching.
- The agent reports what HPD/311 records say; it does not verify current
  building conditions or provide legal advice.
- Scoped to 12 NYC neighborhoods and 2023-present — citywide, full-history
  coverage is a later item.
- No predictive risk scoring in the MVP.
- Multiple 311 complaints about the same building-wide condition on the
  same day are genuine, separate tenant reports, not duplicate data.
- Guardrails use explainable, source-grounded keyword/pattern matching
  rather than a second LLM-as-judge call — a deliberate simplicity/cost
  tradeoff, worth naming as a "if I had more time" improvement.
- Feedback/signup data is stored in local CSV files, which can reset on
  Streamlit Cloud redeploys — treated as pilot-stage, checked/downloaded
  periodically rather than assumed durable.
- Session memory (last address/ZIP) resets each session — no persistent
  user accounts or cross-session memory in the MVP.

## Documentation

- [Two-week project plan](docs/NYC_Apartment_Safety_Assistant_2Week_Plan.md)
- [Retrieval evaluation results](eval/eval_results.md)
