# NYC Apartment Safety Assistant — Phase 1 (Ingestion)

## Current status

| Phase | Status |
|---|---|
| Phase 1: Data ingestion | In progress |
| Phase 2: Retrieval (vector store) | Not started |
| Phase 3: Agent + guardrails | Not started |
| Phase 4: Evaluation | Not started |
| Phase 5: UI + docs | Not started |

## Quickstart

```bash
python -m venv .venv
source .venv/bin/activate    # Windows: .venv\Scripts\Activate.ps1
pip install -r requirements.txt
cp .env.example .env
```

Edit `.env`: set `TARGET_ZIPS` to 1-2 neighborhoods you know well, and set
`MAX_ROWS=500` for your first test run so you're not waiting on a huge pull.

Run the two ingestion scripts:

```bash
cd ingestion
python ingest_hpd_violations.py
python ingest_311_complaints.py
```

You should see progress prints and end up with two files:
- `data/bronze_hpd_violations.json`
- `data/bronze_311_housing_complaints.json`

Each script also prints the field names of one sample record — **look at
these carefully**, since NYC Open Data occasionally renames columns, and your
Phase 2 chunking logic will depend on knowing the real field names.

## What to check before moving to Phase 2

1. Open both JSON files and skim 5-10 records. Do the addresses look sane?
   Are there obvious duplicates or nulls in fields you expect to use?
2. Bump `MAX_ROWS` up (or remove it) once you trust the pipeline, and re-run
   for your real target ZIP codes.
3. Write a short `docs/data_profile.md` noting: row counts, date range
   covered, and anything messy you noticed — this is exactly what your
   friend's SafeEats project did in Phase 1, and it's genuinely useful for
   you later, not just documentation theater.

## Next: Phase 2 (retrieval)

Once you're comfortable with the Bronze data, the next step is chunking
these records into embeddable text and building the vector store. Come back
and I'll scaffold that once you've got real data pulled and skimmed.
