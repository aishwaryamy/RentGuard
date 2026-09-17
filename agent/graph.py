"""
LangGraph agent: retrieve -> generate -> guardrail check -> (retry once if
flagged) -> done, or fall back to raw records if it still fails.
"""

import sys
from pathlib import Path
from typing import TypedDict, Optional

sys.path.append(str(Path(__file__).resolve().parent.parent))

from langgraph.graph import StateGraph, END
from retrieval.query import retrieve
from agent.prompts import SYSTEM_PROMPT
from agent.guardrails import contains_legal_claim, has_citation, contains_absolute_safety_claim
from agent.llm import generate


class AgentState(TypedDict):
    question: str
    zip_code: Optional[str]
    retrieved_docs: list
    answer: str
    guardrail_notes: list
    attempt: int


def retrieve_node(state: AgentState) -> AgentState:
    state["retrieved_docs"] = retrieve(state["question"], zip_code=state.get("zip_code"), top_k=5)
    return state


def generate_node(state: AgentState) -> AgentState:
    docs = state["retrieved_docs"]

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
        f"Question: {state['question']}\n\n"
        f"Answer using only the records above, citing specific dates/classes/types."
    )
    state["answer"] = generate(SYSTEM_PROMPT, user_prompt)
    return state


def guardrail_node(state: AgentState) -> AgentState:
    answer = state["answer"]
    docs = state["retrieved_docs"]
    notes = []

    legal_issues = contains_legal_claim(answer)
    if legal_issues:
        notes.append(f"legal_claim_detected: {legal_issues}")
    safety_overreach = contains_absolute_safety_claim(answer)
    if safety_overreach:
        notes.append(f"absolute_safety_claim: {safety_overreach}")

    if docs and not has_citation(answer, docs):
        notes.append("missing_citation")

    state["guardrail_notes"] = state.get("guardrail_notes", []) + notes
    state["attempt"] = state.get("attempt", 0) + 1
    return state


def route_after_guardrail(state: AgentState) -> str:
    notes = state["guardrail_notes"]
    failed = any(
        n.startswith("legal_claim_detected") or n.startswith("absolute_safety_claim") or n == "missing_citation"
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
        "Your previous answer either made a legal/causal claim or didn't cite "
        "specific records. Rewrite it: report only factual record contents "
        "(violation class, complaint type, dates), with no legal conclusions."
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
    graph.add_edge("generate", "guardrail")
    graph.add_conditional_edges(
        "guardrail",
        route_after_guardrail,
        {"regenerate": "regenerate", "safe_fallback": "safe_fallback", "done": END},
    )
    graph.add_edge("regenerate", "guardrail")
    graph.add_edge("safe_fallback", END)

    return graph.compile()
