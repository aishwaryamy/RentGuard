# NYC Apartment Safety Assistant — Project Plan

An AI agent that helps NYC renters and apartment-hunters research a
building's safety and habitability history before signing a lease, using
real NYC Housing Preservation & Development (HPD) violation records and 311
housing complaints. Unlike a keyword search tool, it answers natural-language
questions — *"has this building had heat complaints in the past year?"*,
*"how does this address compare to others on the block?"* — through a
RAG-grounded conversational agent, with guardrails against unverified legal
claims and a measurable evaluation harness.

This is the AI-native complement to a data-engineering-style project: the
point of this build is the retrieval, agent, guardrail, and evaluation
layers — not the pipeline plumbing underneath them.

## Project goals (MVP)

1. Look up any NYC address's HPD violation history (Class A/B/C, open vs.
   closed) and recent 311 housing complaints.
2. Answer natural-language safety questions grounded strictly in retrieved
   records (RAG), always citing violation IDs and dates.
3. Refuse to make legal or causal claims ("this landlord is breaking the
   law") — a guardrail layer restricts responses to factual reporting of
   city records, not legal conclusions.
4. Provide a measurable eval harness scoring retrieval quality (Precision@k,
   Recall@k, MRR) against a held-out labeled set of addresses.

## Architecture

```text
NYC Open Data
  |-- HPD Housing Maintenance Code Violations (dataset wvxf-dwi5)
  `-- NYC 311 Service Requests (dataset erm2-nwe9), filtered to
      HPD-agency housing complaints (heat/hot water, unsanitary
      conditions, plumbing, pests)
       |
       v
  Python ingestion (Socrata API, paginated, address-normalized)
       |
       v
  Local store: normalized JSON/Parquet (Bronze layer)
       |
       v
  Chunking + embedding pipeline
       |
       v
  Vector store (ChromaDB or FAISS) + structured metadata filter
  (address/BBL, date range, violation class)
       |
       v
  LangGraph agent
    |-- Retrieval tool: vector search + structured filter
    |-- Guardrail layer: blocks legal/causal claims, enforces citation
    |-- Response generator: Claude or OpenAI API
       |
       v
  Eval harness: Precision@k / Recall@k / MRR against a labeled
  address set, logged per run
       |
       v
  FastAPI backend + minimal chat UI (Streamlit)
```

## Data sources

| Source | Dataset ID | Selection | Notes |
|---|---|---|---|
| HPD Housing Maintenance Code Violations | `wvxf-dwi5` | Class A/B/C + I violations, open and closed | The same official record HPD itself publishes; updated daily |
| NYC 311 Service Requests | `erm2-nwe9` | Filtered to Heat/Hot Water, Unsanitary Condition, Plumbing, Paint/Plaster, General Construction, Door/Window | Same underlying dataset as SafeEats, filtered to a different complaint slice |
| (Stretch, if time allows) HPD Multiple Dwelling Registration | — | Owner / managing agent name | Only pursue this if Phases 1-4 finish early — adds landlord-level rollups |

## Two-week phase plan

| Phase | Days | Focus | Deliverable |
|---|---|---|---|
| **Phase 1 — Ingestion** | 1-3 | Pull HPD violations + filtered 311 complaints via the Socrata API for a bounded set of NYC addresses/ZIP codes (start small — one or two neighborhoods, not all of NYC). Normalize address strings and dates. | A local Bronze store (JSON or Parquet) with deduplicated, normalized records, plus a short data-profile note (row counts, date range, known messiness in address fields). |
| **Phase 2 — Retrieval** | 4-6 | Chunk violation/complaint records into embeddable text, build the vector store, and add a structured metadata filter (address, date range, violation class) alongside vector search. | A retrieval function that, given an address, returns the most relevant violation/complaint records with both semantic and structured filtering. |
| **Phase 3 — Agent + guardrails** | 7-9 | Build the LangGraph agent: a retrieval tool, a response generator, and a guardrail step that (a) requires every claim to cite a violation ID/date and (b) refuses legal/causal language ("illegal," "landlord's fault") in favor of factual framing ("HPD recorded a Class C violation for lack of heat on [date]"). | A working conversational agent answerable via CLI or simple script, with test cases showing the guardrail catching at least one legal-claim and one uncited-claim attempt. |
| **Phase 4 — Evaluation** | 10-12 | Hand-label a small set of addresses with known "correct" violation/complaint records. Build an eval script scoring the retrieval step on Precision@5, Recall@10, and MRR. Log results per run so you can show before/after when you tune retrieval. | An eval report (markdown or JSON) with actual numbers — this is your interview talking point, so don't skip it even if the numbers aren't perfect. |
| **Phase 5 — UI + docs** | 13-14 | Wrap the agent in a minimal Streamlit chat interface. Write the README in the same phased style as your friend's project: status table, architecture diagram, data sources, MVP assumptions/exclusions. | A demoable app plus documentation good enough to link from your resume. |

## MVP assumptions and exclusions

Being explicit about these — the way SafeEats does — is itself a signal of
engineering maturity to interviewers:

- Address matching is best-effort text normalization, not authoritative
  BBL (building identifier) matching — state this clearly rather than implying
  precision you don't have.
- The agent reports what HPD/311 records say; it does not verify current
  building conditions or provide legal advice. This should be a visible
  disclaimer in the UI, not just a code comment.
- Scope to 1-2 neighborhoods for the two-week build — citywide coverage is
  a "later" item, not an MVP requirement.
- No predictive risk scoring in the MVP (unlike SafeEats's planned page) —
  that's a good "if I had more time" stretch answer in interviews, not
  something to build now.
- 311 complaint-to-building matching is proximity/address-based, not proof
  of causation — same caveat SafeEats documents for its geospatial matching.

## Suggested repo structure

```text
nyc-apartment-safety-assistant/
|-- ingestion/          # Socrata API pulls, normalization, storage
|-- retrieval/          # chunking, embedding, vector store, structured filter
|-- agent/              # LangGraph agent, guardrail logic, prompts
|-- eval/               # labeled address set, eval harness, run logs
|-- app/                # FastAPI backend + Streamlit UI
|-- docs/
|   |-- architecture.md
|   |-- eval_results.md
|   `-- README.md
|-- tests/
`-- requirements.txt
```

## Why this is a strong interview asset

This project directly demonstrates the skills your target JDs ask for and
that your resume was previously missing: a real evaluation harness with
actual metrics (not just "I built a RAG app"), a guardrail layer with
concrete refusal behavior you can describe, and an agent built with
LangGraph — the same tool you already use professionally. It's also
something you can talk about with genuine personal stakes: you live in NYC
and are describing a tool you'd actually use.

---

## Postscript: what actually happened

This plan was written before the build started. In practice, the project
grew well beyond this original 2-week scope — 12 neighborhoods instead of
2, a full public Streamlit deployment, real address verification, session
memory, and 7 distinct bugs found and fixed through deliberate adversarial
testing (see the main README's Phase 5 section for the full list). The
original phase structure held up well as a roadmap, but the depth of
Phase 5 in particular — hardening the agent against edge cases a real
public user would actually try — ended up being the most valuable part of
the whole build.
