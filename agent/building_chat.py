"""
Answers questions about ONE looked-up building, using only that building's
live HPD/311 records. Reuses the same guardrails as before (legal claims,
'all clear' claims, fabricated addresses, citations), then retries once and
falls back to raw records if the answer still doesn't pass.
"""

import re

from agent.guardrails import (
    contains_absolute_safety_claim,
    contains_legal_claim,
    contains_unlisted_address,
    has_citation,
)
from agent.llm import generate

SYSTEM_PROMPT = """You are RentGuard, an assistant that explains one NYC building's
HPD violation and 311 complaint history to a renter.

Rules you must always follow:
1. Use ONLY the facts in the BUILDING SUMMARY and RECORDS provided. Never add
   outside knowledge about this building, its landlord, or its current condition.
2. Support every claim with the record it came from: write dates as YYYY-MM-DD
   and name the violation class (e.g. "Class C") or the complaint type.
3. Never make legal conclusions or blame the landlord. Do not say anything is
   illegal, unlawful, negligent, or that someone is liable. Report what HPD or
   311 recorded, in neutral wording.
4. Never describe the building as safe, clean, problem-free, or having "no
   issues". Records only show what was reported; absence of records is not
   proof of absence of problems.
5. If the question can't be answered from these records (rent, the landlord's
   behavior, current conditions, other buildings), say so in one sentence and
   suggest what the renter could check instead.
6. Explain code jargon in plain English. Keep answers under about 180 words.
   Use short bullets only when listing several violations.
7. Use the numbers in the BUILDING SUMMARY for counts. If only a subset of
   records is shown, say the list is a subset.
8. Do not mention any street address other than the building's own.
"""

RANK = {"C": 0, "B": 1, "A": 2, "I": 3}


def _date_key(d: str) -> int:
    return -int(d.replace("-", "")) if d else 0


def _trim(text: str, n: int) -> str:
    return text if len(text) <= n else text[: n - 1] + "…"


def _violation_line(v: dict) -> str:
    return (
        f"- VIOLATION | Class {v['class']} | inspected {v['date']} | "
        f"{v['status']} ({v['status_detail']}) | {_trim(v['description'], 220)}"
    )


def _complaint_line(c: dict) -> str:
    detail = f" - {c['detail']}" if c["detail"] else ""
    return f"- COMPLAINT | reported {c['date']} | {c['type']}{detail} | {c['status']}"


def _pretty(name: str) -> str:
    return (name or "").title()


def _summary(report: dict) -> str:
    s, b = report["stats"], report["building"]
    oc = s["open_by_class"]
    return (
        f"BUILDING: {_pretty(b['name'])} (borough: {b.get('borough')}, BBL {b['bbl']})\n"
        f"VIOLATIONS (all time): {s['total']} total; {s['open']} open "
        f"(open Class C: {oc.get('C', 0)}, open Class B: {oc.get('B', 0)}, "
        f"open Class A: {oc.get('A', 0)}); {s['last_12m']} inspected in the last 12 months.\n"
        f"HPD-ROUTED 311 COMPLAINTS: {s['complaints_total']} total; "
        f"{s['complaints_12m']} in the last 12 months; {s['complaints_3y']} in the last 3 years.\n"
        f"MOST RECENT VIOLATION INSPECTION: {s['latest_date'] or 'none'}"
    )


def _select_records(report: dict):
    violations, complaints = report["violations"], report["complaints"]
    open_v = sorted(
        (v for v in violations if v["status"] == "Open"),
        key=lambda v: (RANK.get(v["class"], 9), _date_key(v["date"])),
    )[:30]
    recent_closed = [v for v in violations if v["status"] != "Open"][:15]
    recent_complaints = complaints[:20]
    return open_v + recent_closed, recent_complaints


def _as_docs(violations: list[dict], complaints: list[dict], address: str) -> list[dict]:
    docs = []
    for v in violations:
        docs.append({
            "text": _violation_line(v),
            "metadata": {"date": v["date"], "violation_class": v["class"], "address": address},
        })
    for c in complaints:
        docs.append({
            "text": _complaint_line(c),
            "metadata": {"date": c["date"], "complaint_type": c["type"], "address": address},
        })
    return docs


def _mentions_known_count(answer: str, stats: dict) -> bool:
    keys = ("total", "open", "last_12m", "complaints_total", "complaints_12m", "complaints_3y")
    return any(
        stats[k] > 0 and re.search(rf"\b{stats[k]}\b", answer) for k in keys
    )


def _is_decline(answer: str) -> bool:
    short = len(answer.split()) < 80
    return short and bool(re.search(r"\b(can(?:'|no)t|do(?:es)? not|don't|unable|isn't|not able)\b", answer.lower()))


def _check(answer, docs, source_text, stats, address) -> list[str]:
    notes = []
    legal = contains_legal_claim(answer, source_text=source_text)
    if legal:
        notes.append(f"legal_claim: {legal}")
    if contains_absolute_safety_claim(answer):
        notes.append("all_clear_claim")
    unlisted = contains_unlisted_address(answer, docs, extra_allowed=[address])
    if unlisted:
        notes.append(f"unlisted_address: {unlisted}")
    grounded = has_citation(answer, docs) or _mentions_known_count(answer, stats) or _is_decline(answer)
    if not grounded:
        notes.append("missing_citation")
    return notes


def _fallback_text(report: dict) -> str:
    open_v = sorted(
        (v for v in report["violations"] if v["status"] == "Open"),
        key=lambda v: (RANK.get(v["class"], 9), _date_key(v["date"])),
    )[:5]
    lines = [
        "I couldn't produce an answer that passed my accuracy checks, so here are "
        "this building's most serious open records instead:",
        "",
    ]
    if open_v:
        lines += [_violation_line(v) for v in open_v]
    else:
        lines.append("No open violations are on record for this building.")
    return "\n".join(lines)


def _answer_with_llm(question: str, report: dict) -> dict:
    """Returns {"answer": str, "verified": bool, "notes": list[str]}."""
    stats, building = report["stats"], report["building"]

    if stats["total"] == 0 and stats["complaints_total"] == 0:
        return {
            "answer": (
                "NYC Open Data has no HPD violations or HPD-routed 311 complaints for "
                "this building, so there is nothing for me to analyze. That is not proof "
                "the building is problem-free. It only means nothing was recorded here."
            ),
            "verified": True,
            "notes": [],
        }

    violations, complaints = _select_records(report)
    address = building["name"]
    docs = _as_docs(violations, complaints, address)
    source_text = _summary(report) + "\n" + "\n".join(d["text"] for d in docs)

    shown = len(violations) + len(complaints)
    total = stats["total"] + stats["complaints_total"]
    subset_note = (
        f"\n(Only {shown} of {total} records are shown: the most serious open violations, "
        "then the most recent others.)" if shown < total else ""
    )

    prompt = (
        f"{_summary(report)}\n\n"
        "RECORDS (most serious open violations first, then recent closed violations, "
        "then recent complaints):\n"
        + "\n".join(d["text"] for d in docs)
        + subset_note
        + f"\n\nQuestion: {question}"
    )

    notes_seen: list[str] = []
    text = generate(SYSTEM_PROMPT, prompt, max_tokens=600)
    notes = _check(text, docs, source_text, stats, address)
    if not notes:
        return {"answer": text, "verified": True, "notes": []}

    notes_seen += notes
    correction = (
        f"\n\nYour previous answer failed an automated check ({', '.join(notes)}). "
        "Rewrite it: use only the facts above, cite dates as YYYY-MM-DD with the "
        "violation class or complaint type, make no legal conclusions, never say the "
        "building is safe or has no issues, and mention no other address."
    )
    text = generate(SYSTEM_PROMPT, prompt + correction, max_tokens=600)
    notes = _check(text, docs, source_text, stats, address)
    if not notes:
        return {"answer": text, "verified": True, "notes": notes_seen}

    return {
        "answer": _fallback_text(report),
        "verified": False,
        "notes": notes_seen + notes,
    }


# ---------------------------------------------------------------------------
# Deterministic handling of legal-conclusion questions.
# The LLM path can fail its own guardrails twice and dump raw records, which is
# safe but reads like a malfunction. Legal-judgment questions get a fixed,
# predictable decline instead, plus the facts the records do show.
# ---------------------------------------------------------------------------
_LEGAL_PATTERNS = [
    r"\b(sue|suing|lawsuit|liable|liability|negligen\w*|at fault|unlawful)\b",
    r"\b(landlord|owner|management|building|they)\b.{0,40}\b(illegal|breaking the law|break(?:s)? the law|broke the law|against the law)\b",
    r"\bis (this|it|that)\b.{0,20}\b(illegal|legal|allowed)\b",
    r"\b(withhold|withholding)\b.{0,15}\brent\b",
    r"\b(break|breaking|terminate)\b.{0,15}\b(my )?lease\b",
    r"\b(legal action|legal rights|my rights)\b",
]


def _is_legal_question(question: str) -> bool:
    q = (question or "").lower()
    return any(re.search(pat, q) for pat in _LEGAL_PATTERNS)


def _legal_decline(report: dict) -> dict:
    stats = report["stats"]
    facts = (
        f"What the records do show: {stats['total']} HPD violations since "
        f"{(stats.get('first_date') or 'records began')[:4]}, {stats['open']} still open"
    )
    c_open = stats["open_by_class"].get("C", 0)
    if c_open:
        facts += f" ({c_open} Class C, the most serious category)"
    facts += f", and {stats['complaints_3y']} HPD-routed 311 complaints in the last 3 years."
    return {
        "answer": (
            "I can't make legal judgments, such as whether anyone broke the law or is at "
            "fault. City records only show what HPD inspectors and tenants reported, not "
            "who is legally responsible.\n\n" + facts + "\n\n"
            "For questions about your rights, you can call 311 or contact a tenant "
            "organization or legal aid group."
        ),
        "verified": True,
        "notes": [],
    }


def answer_question(question: str, report: dict) -> dict:
    """Returns {"answer": str, "verified": bool, "notes": list[str]}."""
    if _is_legal_question(question):
        return _legal_decline(report)
    return _answer_with_llm(question, report)
