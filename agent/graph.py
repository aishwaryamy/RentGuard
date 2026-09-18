"""
LangGraph agent: retrieve -> generate -> guardrail check -> (retry once if
flagged) -> done, or fall back to raw records if it still fails.
"""

import re
import sys
from pathlib import Path
from typing import TypedDict, Optional

sys.path.append(str(Path(__file__).resolve().parent.parent))

from langgraph.graph import StateGraph, END
from retrieval.query import retrieve
from agent.prompts import SYSTEM_PROMPT
from agent.guardrails import (
    contains_legal_claim,
    has_citation,
    contains_absolute_safety_claim,
    contains_unlisted_address,
)
from agent.llm import generate
from agent.geocode import verify_address

BYPASS_NOTES = {"no_address_match", "no_records_found"}

PROXIMITY_PATTERNS = [
    r"\bnear\b", r"\bnearby\b", r"\bsurrounding\b", r"\baround\b",
    r"\bclose to\b", r"\bvicinity\b", r"\bin the area\b",
]


class AgentState(TypedDict):
    question: str
    zip_code: Optional[str]
    retrieved_docs: list
    answer: str
    guardrail_notes: list
    attempt: int
    resolved_address: Optional[str]
    resolved_zip: Optional[str]
    reference_address: Optional[str]


def retrieve_node(state: AgentState) -> AgentState:
    state["retrieved_docs"] = retrieve(state["question"], zip_code=state.get("zip_code"), top_k=5)
    return state


def _extract_street_number(text: str) -> str | None:
    match = re.search(r"\b\d{1,5}\b", text)
    return match.group(0) if match else None


def _is_proximity_question(text: str) -> bool:
    lower = text.lower()
    return any(re.search(p, lower) for p in PROXIMITY_PATTERNS)


def generate_node(state: AgentState) -> AgentState:
    docs = state["retrieved_docs"]
    question = state["question"]
    state.setdefault("resolved_address", None)
    state.setdefault("resolved_zip", None)

    is_proximity = _is_proximity_question(question)
    street_number = None if is_proximity else _extract_street_number(question)

    if street_number and docs:
        matching = [d for d in docs if street_number in d["metadata"].get("address", "")]
        if not matching:
            geo = verify_address(question)
            if geo["status"] == "not_found":
                state["answer"] = (
                    "That doesn't appear to be a valid address — I checked "
                    "it against USPS address data and found no match. "
                    "Double-check the spelling or street number."
                )
            elif geo["status"] == "found":
                state["answer"] = (
                    f"That's a valid address ({geo['matched_address']}), but "
                    "I have no HPD violation or 311 complaint records for it "
                    "in my current data."
                )
                state["resolved_address"] = geo["matched_address"]
                state["resolved_zip"] = geo.get("zip")
            else:
                state["answer"] = (
                    "I couldn't find any records for that address in my "
                    "current data."
                )
            state["guardrail_notes"] = ["no_address_match"]
            state["retrieved_docs"] = []
            return state
        docs = matching
        state["resolved_address"] = matching[0]["metadata"].get("address")
        state["resolved_zip"] = matching[0]["metadata"].get("zip")

    if not docs:
        state["answer"] = (
            "I don't have any HPD violation or 311 complaint records matching "
            "that address/ZIP in my current data. I can't answer based on "
            "records I don't have."
        )
        state["guardrail_notes"] = ["no_records_found"]
        return state

    context = "\n\n".join(f"- {d['text']}" for d in docs)
    user_prompt = (
        f"Records:\n{context}\n\n"
        f"Question: {question}\n\n"
        f"Answer using only the records above, citing specific dates/classes/types. "
        f"Do not mention any address, street, or location that is not one of the "
        f"addresses listed in the records above."
    )
    state["answer"] = generate(SYSTEM_PROMPT, user_prompt)
    state["retrieved_docs"] = docs
    if not state.get("resolved_zip") and docs:
        state["resolved_zip"] = docs[0]["metadata"].get("zip")
    return state


def route_after_generate(state: AgentState) -> str:
    notes = state.get("guardrail_notes", [])
    if any(n in BYPASS_NOTES for n in notes):
        return "done"
    return "check"


def guardrail_node(state: AgentState) -> AgentState:
    answer = state["answer"]
    docs = state["retrieved_docs"]
    notes = []

    source_text = "\n".join(d["text"] for d in docs) if docs else ""
    legal_issues = contains_legal_claim(answer, source_text=source_text)
    if legal_issues:
        notes.append(f"legal_claim_detected: {legal_issues}")

    safety_overreach = contains_absolute_safety_claim(answer)
    if safety_overreach:
        notes.append(f"absolute_safety_claim: {safety_overreach}")

    if docs:
        extra_allowed = [state.get("reference_address")] if state.get("reference_address") else None
        unlisted = contains_unlisted_address(answer, docs, extra_allowed=extra_allowed)
        if unlisted:
            notes.append(f"hallucinated_address: {unlisted}")

        if not has_citation(answer, docs):
            notes.append("missing_citation")

    state["guardrail_notes"] = state.get("guardrail_notes", []) + notes
    state["attempt"] = state.get("attempt", 0) + 1
    return state


def route_after_guardrail(state: AgentState) -> str:
    notes = state["guardrail_notes"]
    failed = any(
        n.startswith("legal_claim_detected")
        or n.startswith("absolute_safety_claim")
        or n.startswith("hallucinated_address")
        or n == "missing_citation"
        for n in notes
    )

    if failed and state["attempt"] < 2:
        return "regenerate"
    if failed:
        return "safe_fallback"
    return "done"


def regenerate_node(state: AgentState) -> AgentState:
    docs = state["retrieved_docs"]
    context = "\n\n".join(f"- {d['text']}" for d in docs)
    correction = (
        "Your previous answer had a problem: it may have made a legal/causal "
        "claim, an absolute 'no issues'/'safe' claim, mentioned an address "
        "not present in the records below, or didn't cite specific records. "
        "Rewrite it using ONLY the exact addresses, dates, and classes/types "
        "shown in the records below — do not introduce any other address."
    )
    user_prompt = f"Records:\n{context}\n\nQuestion: {state['question']}\n\n{correction}"
    state["answer"] = generate(SYSTEM_PROMPT, user_prompt)
    return state


def safe_fallback_node(state: AgentState) -> AgentState:
    docs = state["retrieved_docs"]
    state["answer"] = (
        "I found relevant records but couldn't generate a response that met "
        "citation and factual-accuracy requirements. Here are the raw records "
        "instead:\n\n" + "\n\n".join(d["text"] for d in docs)
    )
    return state


def build_graph():
    graph = StateGraph(AgentState)
    graph.add_node("retrieve", retrieve_node)
    graph.add_node("generate", generate_node)
    graph.add_node("guardrail", guardrail_node)
    graph.add_node("regenerate", regenerate_node)
    graph.add_node("safe_fallback", safe_fallback_node)

    graph.set_entry_point("retrieve")
    graph.add_edge("retrieve", "generate")
    graph.add_conditional_edges(
        "generate",
        route_after_generate,
        {"done": END, "check": "guardrail"},
    )
    graph.add_conditional_edges(
        "guardrail",
        route_after_guardrail,
        {"regenerate": "regenerate", "safe_fallback": "safe_fallback", "done": END},
    )
    graph.add_edge("regenerate", "guardrail")
    graph.add_edge("safe_fallback", END)

    return graph.compile()
