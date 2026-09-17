"""
Simple, explainable guardrails — not a black box. Two checks:
1. Does the answer contain legal/causal language it shouldn't?
2. Does the answer actually cite something from the retrieved records?
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


def contains_legal_claim(text: str) -> list[str]:
    """Return any legal/causal claim patterns found in the text."""
    lower = text.lower()
    return [p for p in LEGAL_CLAIM_PATTERNS if re.search(p, lower)]

ABSOLUTE_SAFETY_PATTERNS = [
    r"\bno issues\b",
    r"\bissue-free\b",
    r"\bclean record\b",
    r"\bhas no complaints\b",
    r"\bcompletely safe\b",
    r"\bsafest\b",
]

def contains_absolute_safety_claim(text: str) -> list[str]:
    """
    Catches claims that a building has zero issues in absolute terms — this
    dataset can only show reported complaints/violations, never confirm a
    building has none, so any such claim is an overreach the guardrail
    should catch.
    """
    lower = text.lower()
    return [p for p in ABSOLUTE_SAFETY_PATTERNS if re.search(p, lower)]

def has_citation(text: str, retrieved_docs: list[dict]) -> bool:
    """
    Does the answer reference at least one date, violation class, or
    complaint type that actually appears in the retrieved documents?
    """
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
