"""
Simple, explainable guardrails — not a black box.
"""

import re

LEGAL_CLAIM_PATTERNS = [
    r"\bbreaking the law\b",
    r"\billegal(ly)?\b",
    r"\bliable\b",
    r"\bguilty\b",
    r"\bsue\b",
    r"\blawsuit\b",
    r"\bmust legally\b",
    r"\brequired by law\b",
    r"\byour landlord (is|was) required\b",
]

ABSOLUTE_SAFETY_PATTERNS = [
    r"\bno issues\b",
    r"\bissue-free\b",
    r"\bclean record\b",
    r"\bhas no complaints\b",
    r"\bcompletely safe\b",
    r"\bsafest\b",
]

ADDRESS_PATTERN = re.compile(
    r"\d{1,5}[-\d]*\s+(?:[A-Z0-9]+\s+){0,4}"
    r"(?:STREET|ST|AVENUE|AVE|PLACE|PL|PARKWAY|PKWY|BOULEVARD|BLVD|DRIVE|DR|ROAD|RD|LANE|LN)\b"
)


def contains_legal_claim(text: str, source_text: str = "") -> list[str]:
    """
    Flags legal/causal language in the answer, UNLESS the same word already
    appears in the source records themselves — official HPD/311 violation
    descriptions legitimately use words like "illegal" (e.g. "illegal
    fastening") as part of their own code-violation terminology. Quoting or
    paraphrasing that source language is fine; the model independently
    asserting a legal conclusion in its own words is not.
    """
    lower = text.lower()
    source_lower = source_text.lower()
    flagged = []
    for pattern in LEGAL_CLAIM_PATTERNS:
        match = re.search(pattern, lower)
        if match and match.group(0) not in source_lower:
            flagged.append(pattern)
    return flagged


def contains_absolute_safety_claim(text: str) -> list[str]:
    lower = text.lower()
    return [p for p in ABSOLUTE_SAFETY_PATTERNS if re.search(p, lower)]


def _leading_number(addr: str) -> str | None:
    match = re.match(r"\s*(\d{1,5})", addr)
    return match.group(1) if match else None


def contains_unlisted_address(text: str, retrieved_docs: list[dict], extra_allowed: list[str] | None = None) -> list[str]:
    known_addresses = [d["metadata"].get("address", "") for d in retrieved_docs]
    if extra_allowed:
        known_addresses += [a for a in extra_allowed if a]

    known_numbers = {n for n in (_leading_number(a) for a in known_addresses) if n}

    found = ADDRESS_PATTERN.findall(text.upper())
    unlisted = []
    for candidate in found:
        candidate = candidate.strip()
        num = _leading_number(candidate)
        if num and num in known_numbers:
            continue
        unlisted.append(candidate)
    return unlisted


def has_citation(text: str, retrieved_docs: list[dict]) -> bool:
    if not retrieved_docs:
        return False

    lower = text.lower()
    for doc in retrieved_docs:
        meta = doc["metadata"]
        date = meta.get("date", "")
        if date and date in text:
            return True
        violation_class = meta.get("violation_class")
        if violation_class and f"class {violation_class.lower()}" in lower:
            return True
        complaint_type = meta.get("complaint_type")
        if complaint_type and complaint_type.lower() in lower:
            return True
    return False
