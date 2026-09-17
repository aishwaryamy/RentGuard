"""
Phase 5: Streamlit chat interface for RentGuard.

Run from the project root:
    streamlit run app/streamlit_app.py
"""

import csv
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

import pandas as pd
import streamlit as st

try:
    if "OPENAI_API_KEY" in st.secrets:
        os.environ["OPENAI_API_KEY"] = st.secrets["OPENAI_API_KEY"]
except FileNotFoundError:
    pass

from agent.graph import build_graph

PROJECT_ROOT = Path(__file__).resolve().parent.parent
MAX_QUESTIONS_PER_SESSION = 5
FEEDBACK_EMAIL = "aishwaryamy20@gmail.com"
SIGNUPS_PATH = PROJECT_ROOT / "data" / "signups.csv"
FEEDBACK_PATH = PROJECT_ROOT / "data" / "feedback.csv"

ZIP_LABELS = {
    "10025": "Upper West Side, Manhattan",
    "10009": "East Village, Manhattan",
    "10032": "Washington Heights, Manhattan",
    "11201": "Brooklyn Heights, Brooklyn",
    "11215": "Park Slope, Brooklyn",
    "11217": "Prospect Heights, Brooklyn",
    "11238": "Clinton Hill, Brooklyn",
    "11211": "Williamsburg, Brooklyn",
    "11101": "Long Island City, Queens",
    "11373": "Elmhurst, Queens",
    "10453": "Highbridge, Bronx",
    "10462": "Parkchester, Bronx",
}

SUGGESTED_QUESTIONS = [
    "Has this building had heat complaints?",
    "Any mold or pest issues reported here?",
    "What's the most common complaint in this area?",
    "Are there any open (unresolved) violations?",
]


def extract_zip_from_text(text: str) -> str | None:
    match = re.search(r"\b1[01][0-9]{3}\b", text)
    return match.group(0) if match else None


st.set_page_config(page_title="RentGuard — NYC Apartment Safety", page_icon="🏠", layout="wide")

# ---------- Styling ----------
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,400;9..144,600&family=Public+Sans:wght@400;500;600&display=swap');

:root {
    --bg-navy: #0F1F35;
    --bg-navy-light: #16283F;
    --accent-brass: #C99A44;
    --text-cream: #F2EFE9;
}

.stApp {
    background-color: var(--bg-navy);
    background-image:
        repeating-linear-gradient(0deg, rgba(201,154,68,0.045) 0px, rgba(201,154,68,0.045) 1px, transparent 1px, transparent 64px),
        repeating-linear-gradient(90deg, rgba(201,154,68,0.045) 0px, rgba(201,154,68,0.045) 1px, transparent 1px, transparent 64px);
}

html, body, [class*="css"] {
    font-family: 'Public Sans', sans-serif;
    color: var(--text-cream);
}

h1, h2, h3 {
    font-family: 'Fraunces', serif;
    font-weight: 600;
    color: var(--text-cream) !important;
}

section[data-testid="stSidebar"] {
    background-color: var(--bg-navy-light);
    border-right: 1px solid rgba(201,154,68,0.2);
}

.stButton button {
    background-color: transparent;
    border: 1px solid var(--accent-brass);
    color: var(--accent-brass);
    border-radius: 4px;
}
.stButton button:hover {
    background-color: var(--accent-brass);
    color: var(--bg-navy);
}

[data-testid="stChatInput"] {
    border: 1px solid rgba(201,154,68,0.35);
}
</style>
""", unsafe_allow_html=True)

# ---------- Header ----------
st.markdown("# 🏠 RentGuard")
st.markdown("NYC apartment safety history, grounded in real HPD and 311 records")

st.warning(
    "**Not legal advice.** RentGuard reports what NYC HPD and 311 records "
    "say — it does not verify current building conditions, does not make "
    "legal determinations, and is not a substitute for consulting a "
    "housing attorney or tenant advocacy organization.",
    icon="⚠️",
)

# ---------- Session state ----------
if "graph" not in st.session_state:
    st.session_state.graph = build_graph()
if "messages" not in st.session_state:
    st.session_state.messages = []
if "question_count" not in st.session_state:
    st.session_state.question_count = 0
if "pending_question" not in st.session_state:
    st.session_state.pending_question = None
if "loaded_from_link" not in st.session_state:
    st.session_state.loaded_from_link = False

# ---------- Load a shared link (?zip=...&q=...) only on a genuinely fresh session ----------
qp = st.query_params
if not st.session_state.messages and not st.session_state.loaded_from_link and qp.get("q"):
    st.session_state.pending_question = qp.get("q")
    st.session_state.shared_zip = qp.get("zip") or None
    st.session_state.loaded_from_link = True

# ---------- Sidebar ----------
with st.sidebar:
    st.subheader("Filter")
    zip_options = ["All neighborhoods"] + [f"{z} — {label}" for z, label in ZIP_LABELS.items()]
    default_index = 0
    shared_zip = st.session_state.get("shared_zip")
    if shared_zip:
        for i, opt in enumerate(zip_options):
            if opt.startswith(shared_zip):
                default_index = i
                break

    zip_choice = st.selectbox("Neighborhood / ZIP", options=zip_options, index=default_index)
    zip_code = None if zip_choice == "All neighborhoods" else zip_choice.split(" — ")[0]

    st.divider()
    st.caption(f"Questions used this session: {st.session_state.question_count}/{MAX_QUESTIONS_PER_SESSION}")
    st.caption("Data: NYC HPD Housing Maintenance Code Violations and NYC 311 Service Requests, 2023–present.")

# ---------- Tabs ----------
tab_chat, tab_map, tab_resources, tab_feedback, tab_about = st.tabs(
    ["💬 Chat", "🗺️ Coverage & Stats", "📚 Tenant Resources", "📣 Feedback & Updates", "ℹ️ About"]
)

# ---------- Chat tab ----------
with tab_chat:
    st.caption("Try one of these, or ask your own question:")
    cols = st.columns(len(SUGGESTED_QUESTIONS))
    for col, q in zip(cols, SUGGESTED_QUESTIONS):
        if col.button(q, use_container_width=True, disabled=st.session_state.question_count >= MAX_QUESTIONS_PER_SESSION):
            st.session_state.pending_question = q

    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])
            if msg.get("guardrail_notes"):
                st.caption(f"Guardrail notes: {msg['guardrail_notes']}")

    if st.session_state.question_count >= MAX_QUESTIONS_PER_SESSION:
        st.error(f"You've reached the {MAX_QUESTIONS_PER_SESSION}-question limit for this session. Refresh the page to start a new session.")
    else:
        typed_question = st.chat_input("Ask about a building's safety history...")
        question = typed_question or st.session_state.pending_question
        st.session_state.pending_question = None

        if question:
            effective_zip = zip_code or extract_zip_from_text(question)

            st.session_state.question_count += 1
            st.session_state.messages.append({"role": "user", "content": question})

            st.query_params["q"] = question
            if effective_zip:
                st.query_params["zip"] = effective_zip

            with st.chat_message("user"):
                st.markdown(question)
                if effective_zip:
                    st.caption(f"Filtered to ZIP {effective_zip}")

            with st.chat_message("assistant"):
                with st.spinner("Searching records..."):
                    result = st.session_state.graph.invoke({
                        "question": question,
                        "zip_code": effective_zip,
                        "retrieved_docs": [],
                        "answer": "",
                        "guardrail_notes": [],
                        "attempt": 0,
                    })
                st.markdown(result["answer"])
                if result["guardrail_notes"]:
                    st.caption(f"Guardrail notes: {result['guardrail_notes']}")

            st.session_state.messages.append({
                "role": "assistant",
                "content": result["answer"],
                "guardrail_notes": result["guardrail_notes"],
            })
            st.rerun()

    if st.session_state.messages:
        st.divider()
        st.caption("🔗 Want to share this? Copy the URL from your browser's address bar — it links directly to this question and filter.")

# ---------- Coverage & Stats tab ----------
with tab_map:
    st.subheader("Where RentGuard has data")
    st.caption("Real 311 housing complaint locations currently indexed — this is what 'coverage' actually means, not a marketing claim.")

    complaints_path = PROJECT_ROOT / "data" / "bronze_311_housing_complaints.json"

    if complaints_path.exists():
        complaints = json.load(open(complaints_path))
        map_rows = [
            {"lat": float(c["latitude"]), "lon": float(c["longitude"])}
            for c in complaints
            if c.get("latitude") and c.get("longitude")
        ]
        if map_rows:
            df = pd.DataFrame(map_rows)
            st.map(df, size=15, color="#C99A44")
            st.caption(f"{len(map_rows)} complaint locations shown (of {len(complaints)} total records).")
        else:
            st.info("No coordinate data found in the current dataset.")

        st.divider()
        st.subheader("Most common complaint types")
        complaint_df = pd.DataFrame(complaints)
        if zip_code:
            complaint_df = complaint_df[complaint_df["incident_zip"] == zip_code]
            st.caption(f"Showing {ZIP_LABELS.get(zip_code, zip_code)} only — change the sidebar filter to see other areas.")
        else:
            st.caption("Showing all indexed neighborhoods — pick one in the sidebar to narrow this down.")

        if not complaint_df.empty:
            type_counts = complaint_df["complaint_type"].value_counts()
            st.bar_chart(type_counts)
        else:
            st.info("No complaints indexed for this filter yet.")
    else:
        st.info("Data not found — run the ingestion pipeline first.")

    st.divider()
    st.write("**Neighborhoods currently covered:**")
    for z, label in ZIP_LABELS.items():
        st.write(f"- {label} ({z})")

# ---------- Resources tab ----------
with tab_resources:
    st.subheader("Real help beyond what this tool can offer")
    st.caption("RentGuard reports city records, not legal advice. If you're dealing with an active habitability issue, these are real next steps.")
    st.markdown("""
- **[NYC 311](https://portal.311.nyc.gov/)** — file a new complaint about heat, pests, mold, or other conditions directly with the city.
- **[HPD Online](https://hpdonline.hpdnyc.org/)** — look up any NYC building's full violation history directly from the source.
- **[Housing Court Answers](https://housingcourtanswers.org/)** — free help understanding NYC housing court and tenant rights, not affiliated with the city.
- **[Met Council on Housing](https://www.metcouncilonhousing.org/)** — a tenant rights hotline and counseling organization.
- **[NYC Tenant Resource Portal](https://www.nyc.gov/site/tenantresourceportal/index.page)** — the city's own guide to tenant rights and resources.
    """)

# ---------- Feedback & Updates tab ----------
with tab_feedback:
    st.subheader("Tell us what you think")
    st.caption("This is an early pilot — real feedback directly shapes what gets built next.")

    with st.form("feedback_form", clear_on_submit=True):
        feedback_text = st.text_area("What worked, what didn't, or what's missing?")
        feedback_email = st.text_input("Your email (optional, if you want a reply)")
        submitted = st.form_submit_button("Send feedback")
        if submitted and feedback_text.strip():
            FEEDBACK_PATH.parent.mkdir(parents=True, exist_ok=True)
            is_new = not FEEDBACK_PATH.exists()
            with open(FEEDBACK_PATH, "a", newline="") as f:
                writer = csv.writer(f)
                if is_new:
                    writer.writerow(["timestamp", "feedback", "email"])
                writer.writerow([datetime.now(timezone.utc).isoformat(), feedback_text.strip(), feedback_email.strip()])
            st.success("Thanks — this was saved and will be read.")
        elif submitted:
            st.warning("Add a bit of feedback text before submitting.")

    st.caption(f"Prefer email? Reach out directly: {FEEDBACK_EMAIL}")

    st.divider()

    st.subheader("Get notified when your neighborhood is added")
    st.caption("RentGuard currently covers 12 neighborhoods. Leave your email and the ZIP you care about, and you'll hear when it expands there.")

    with st.form("signup_form", clear_on_submit=True):
        signup_email = st.text_input("Email")
        signup_zip = st.text_input("ZIP code you're interested in")
        signup_submitted = st.form_submit_button("Notify me")
        if signup_submitted and signup_email.strip():
            SIGNUPS_PATH.parent.mkdir(parents=True, exist_ok=True)
            is_new = not SIGNUPS_PATH.exists()
            with open(SIGNUPS_PATH, "a", newline="") as f:
                writer = csv.writer(f)
                if is_new:
                    writer.writerow(["timestamp", "email", "zip_of_interest"])
                writer.writerow([datetime.now(timezone.utc).isoformat(), signup_email.strip(), signup_zip.strip()])
            st.success("You're on the list.")
        elif signup_submitted:
            st.warning("Add an email before submitting.")

# ---------- About tab ----------
with tab_about:
    st.subheader("About RentGuard")
    st.markdown("""
RentGuard is an AI-native tool for researching a NYC building's housing
safety history before signing a lease, built on real HPD violation and 311
complaint records.

**How it works:** your question is matched against real city records using
semantic search, then an AI model answers using only what those records
say — with a guardrail layer that blocks legal claims, blocks absolute
"no issues" style claims, and requires citations, falling back to raw
records rather than guessing when it can't answer confidently.

**Current limitations (by design, for this pilot):**
- Covers 12 neighborhoods across all 5 boroughs, not the full city yet.
- Records from 2023–present only.
- Reports what the city recorded — doesn't verify current conditions, and
  cannot confirm any building has zero complaints ever filed.

**Built by:** [Aishwarya M Y](https://aishwaryamy.github.io/) — [source code on GitHub](https://github.com/aishwaryamy/RentGuard)
    """)
