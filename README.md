# RentGuard (NYC Apartment Safety Assistant)

RentGuard helps NYC renters research a building before signing a lease. Type any NYC
address and it pulls that building's live HPD housing violations and 311 housing
complaints from NYC Open Data, summarizes them in plain English, and lets you ask
questions about the building. Answers are grounded in the building's actual records,
cited, and never make legal claims.

**Live app:** [rentguard.streamlit.app](https://rentguard-fwpwhgu6y7iwhzbozcefml.streamlit.app/)

> RentGuard reports what NYC's HPD and 311 records say. It can't verify current
> conditions and isn't legal advice.

## Why I built it

I was apartment-hunting in NYC and kept wondering what I'd actually be signing up for.
The data is public, but it's scattered across datasets and hard to read. I wanted a tool I'd
use myself, and I wanted to build it so it can't mislead people: a wrong answer in a
safety tool is worse than no answer.

## How it works (v2, the deployed app)

1. **Resolve and verify the address.** NYC Planning Labs' Geosearch API turns the typed
   address into a BBL (borough-block-lot, the city's tax-lot ID). A verification layer checks
   the result against what the user typed, and refuses out-of-NYC input (see Bug #8).
2. **Pull live records by BBL.** HPD violations (`wvxf-dwi5`) and HPD-routed 311 complaints
   (`erm2-nwe9`) are fetched from Socrata by exact BBL, so there is no fuzzy matching on
   address strings. Results are cached for an hour.
3. **Explain and answer.** The report tab shows totals, open violations by class, recent
   activity and the records. The chat answers questions using only that building's records, behind
   guardrails.

```text
User types an address
   |
   v
lookup/resolve.py      scope gate -> Geosearch -> verify each candidate -> ok / confirm / refuse
   |  (verified BBL only)
   v
lookup/live.py         Socrata: HPD violations + HPD 311 complaints by exact BBL (retry, cache)
   |
   v
Report tab             stats + records, plain-English headline
   |
   v
agent/building_chat.py building-scoped LLM answer (gpt-4o-mini)
   |
   v
agent/guardrails.py    legal-claim, absolute-safety-claim, unlisted-address, citation checks
   |                   fail -> retry once -> fall back to the raw records
   v
Streamlit UI           4 tabs, shareable ?address= links, session question cap
```

**Key design insight:** v1 used RAG (embeddings and a vector store). For this product the
question is always about one exact building, so a structured lookup by BBL beats vector
search: it is exact, always current, and needs no index. v2 replaced RAG with structured
retrieval and kept the LLM only for explanation. The v1 pipeline and its evaluation are kept in
the repo for reference.

## Features

- Live lookup for any NYC address (all five boroughs), always current
- Building report: violations by class (A/B/C), open vs. closed, last-12-month activity, 311 complaints
- Ask-about-this-building chat with citations and guardrails
- Tenant toolkit (what to do next, who to call)
- Shareable links: `?address=219+13th+St,+Brooklyn` reproduces a report
- Address verification that refuses to guess (Bug #8)
- Session question cap (8) to bound API cost

## Bug #8: out-of-NYC address silently resolved to a NYC building

**Symptom.** Searching `47 Grace St, Jersey City, NJ` returned a full report for
`47 Grace Court, Brooklyn Heights 11201` (BBL 3002510029): a different building, in a
different state.

**Root cause.** Geosearch only contains NYC and fuzzy-matches whatever it is given, so it
always returns its closest guess. My lookup trusted the top hit and never compared it with what the
user typed. The app was confidently wrong, which is worse for a safety tool than an error.

**Fix: never trust the geocoder, verify it** (`lookup/resolve.py`):

1. **Scope gate.** Before any API call, input naming a non-NYC state, city or ZIP
   (NJ, Jersey City, 07307, Seattle WA 98101, Yonkers NY 10701) is refused with an
   explanation. Nothing is guessed.
2. **Verification.** Every candidate is compared with the typed text on house number, street
   name, street type, E/W direction, borough and ZIP. A contradiction on any of them rejects it.
   This works for any address, not just known cities, so `1 Pine St, Seattle` returns no match.
3. **Confidence tiers.** Only an exact agreement loads automatically. A near miss (wrong street type,
   missing direction, unrecognized locality) is shown as "Did you mean...?" and needs an explicit
   click. If nothing agrees, the app says so.

| Typed | Result |
|---|---|
| `47 Grace St, Jersey City, NJ` | refused: outside NYC |
| `47 Grace St, Brooklyn` | "Did you mean 47 Grace Court?" (click required) |
| `48 Grace Court, Brooklyn` | no match (wrong house number) |
| `219 13th St, Brooklyn 10001` | no match (ZIP contradicts) |
| `100 Main St` | asks which borough (exists in two) |
| `47 Grace Court, Brooklyn, NY 11201` | loads the report |

**Edge cases covered.** `Ct` means Court, not Connecticut. A 5-digit house number is not a ZIP.
`E 13th St` equals `East 13th Street`. `NY 10701` (Yonkers) is New York State but not NYC.

**Tests.** `tests/test_resolve.py` runs 32 offline cases against a fake geocoder that mimics
Pelias's always-return-something behavior. `tests/smoke_resolve.py` runs the key cases against the
real API (all pass).

**Lesson.** For an application that reports safety information, a wrong answer is worse than no
answer. Any upstream fuzzy matcher needs a verification layer that can say "I don't know".

## Earlier bugs found through adversarial testing (v1)

I tested by deliberately asking edge-case and out-of-scope questions, not just happy paths.

1. *Ambiguous reference hallucination:* "this building" with no address made the model pick an unrelated record. Fixed by detecting ambiguous references and asking for clarification.
2. *Absolute safety-claim overreach:* "no violation issued" was conflated with "confirmed zero complaints." Fixed with a guardrail and a system-prompt rule separating "no reported issues" from "issue-free."
3. *Out-of-scope location leakage:* a Jersey City address returned NYC records. Fixed with scope detection (the precursor to Bug #8).
4. *Ungrounded fallback records:* the fallback showed records without checking they matched the address. Fixed by requiring a street-number match.
5. *Address hallucination:* the model invented an address in its summary. Fixed with a guardrail comparing every address in an answer against the retrieved records' street numbers.
6. *Proximity-question misfire:* "what's near that address?" was treated as an exact-address lookup. Fixed by detecting proximity language.
7. *False-positive legal-claim blocking:* official HPD text legitimately contains words like "illegal." Fixed with a source-grounded check: flagged language already present in the records is a citation, not model overreach.

Bug #8 showed that the same class of problem (trusting an upstream fuzzy system) also exists
before the LLM is called, so it needs its own verification layer.

## Project history

| Phase | Status | Result |
|---|---|---|
| 1. Ingestion | Complete | HPD violations and 311 complaints pulled via Socrata across 12 ZIPs, with retry-safe ingestion. |
| 2. Retrieval (RAG) | Complete | Chunked, embedded (all-MiniLM-L6-v2), indexed in ChromaDB, with semantic search plus metadata filters. |
| 3. Agent + guardrails | Complete | LangGraph agent (retrieve, generate, guardrail, retry or fallback) on gpt-4o-mini. |
| 4. Evaluation | Complete | Precision@5 = 1.000, MRR = 1.000, Recall@10 = 0.175 (ceiling 0.188), over 7 labeled queries. |
| 5. Public deployment | Complete | Streamlit Community Cloud, adversarial testing (bugs 1-7). |
| 6. v2 live lookup | Complete | Any-NYC-address coverage via BBL lookup, redesigned UI, address verification (Bug #8). |

v1 evaluation details are in [eval/eval_results.md](eval/eval_results.md).

## Data sources

| Source | Dataset | Use |
|---|---|---|
| HPD Housing Maintenance Code Violations | `wvxf-dwi5` | Violations by BBL (class, inspection date, status, description) |
| NYC 311 Service Requests | `erm2-nwe9` | HPD-routed housing complaints by BBL |
| NYC Planning Labs Geosearch | `geosearch.planninglabs.nyc` | Address to BBL/BIN, NYC-only |

## Repository structure

```text
nyc-apartment-safety-assistant/
|-- app/streamlit_app.py       # v2 UI: search, report, chat, toolkit, about
|-- lookup/
|   |-- live.py                # Geosearch + Socrata by BBL, stats, report
|   `-- resolve.py             # address verification (Bug #8)
|-- agent/
|   |-- building_chat.py       # building-scoped chat
|   |-- guardrails.py          # legal / absolute-claim / address / citation checks
|   `-- llm.py                 # OpenAI wrapper
|-- tests/
|   |-- test_resolve.py        # 32 offline cases
|   |-- smoke_resolve.py       # live API check
|   `-- smoke_lookup.py        # live lookup check
|-- ingestion/ retrieval/ eval/ # v1 RAG pipeline and evaluation (reference)
|-- .streamlit/config.toml
|-- requirements.txt           # lean runtime deps for deployment
|-- requirements-dev.txt       # full v1 set (embeddings, ChromaDB, LangGraph)
`-- README.md
```

## Run locally

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # add OPENAI_API_KEY (and optionally SOCRATA_APP_TOKEN)
streamlit run app/streamlit_app.py
```

Tests (no keys needed for the first):

```bash
python -m tests.test_resolve     # offline
python -m tests.smoke_resolve    # live Geosearch
python -m tests.smoke_lookup     # live lookup
```

## Deployment

Streamlit Community Cloud, connected to `main`, main file `app/streamlit_app.py`. Secrets
(`OPENAI_API_KEY`, optional `SOCRATA_APP_TOKEN`) live in Streamlit's secrets manager, never in
the repo. It auto-redeploys on push.

## Known limitations

- Records attach to the whole tax lot (BBL). For large complexes or condos, a report covers the
  lot, not one unit.
- Data is what was reported or recorded. No record doesn't prove a building is problem-free.
- 311 matching is by BBL; a complaint is not proof of cause.
- Guardrails are explainable pattern and source-grounded checks, not an LLM-as-judge (a deliberate
  simplicity and cost tradeoff; a second-model judge is a natural next step).
- The address verifier errs toward asking or refusing; some unusual real spellings may need a
  second try.
- No accounts or cross-session memory.

## Documentation

- [Two-week project plan](docs/NYC_Apartment_Safety_Assistant_2Week_Plan.md)
- [v1 retrieval evaluation](eval/eval_results.md)
