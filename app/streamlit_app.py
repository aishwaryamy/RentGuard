"""
RentGuard: look up any NYC building's housing-violation history.

Run from the project root:
    streamlit run app/streamlit_app.py
"""

import csv
import html
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

import pandas as pd
import streamlit as st

try:
    for _key in ("OPENAI_API_KEY", "SOCRATA_APP_TOKEN"):
        if _key in st.secrets:
            os.environ[_key] = st.secrets[_key]
except Exception:
    pass  # no secrets.toml locally; .env is used instead

from agent.building_chat import answer_question
from lookup.live import LookupFailed, build_report
from lookup.resolve import resolve_address

PROJECT_ROOT = Path(__file__).resolve().parent.parent
FEEDBACK_PATH = PROJECT_ROOT / "data" / "feedback.csv"
FEEDBACK_EMAIL = "aishwaryamy20@gmail.com"
MAX_QUESTIONS_PER_SESSION = 8

EXAMPLES = ["219 13th St, Brooklyn", "2612 Broadway, Manhattan", "537 E 13th St, Manhattan"]
CHAT_SUGGESTIONS = [
    "What are the most serious open violations?",
    "Any heat or hot water problems?",
    "Any pests or mold?",
    "Explain these violations in plain English",
]
CLASS_COLORS = {"A": "#3E6AA8", "B": "#C77700", "C": "#B3261E", "I": "#6B7280"}
CLASS_RANK = {"C": 0, "B": 1, "A": 2, "I": 3}

st.set_page_config(
    page_title="RentGuard: NYC building safety lookup",
    page_icon="🏢",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ------------------------------------------------------------------ styling
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,500;9..144,600&family=Public+Sans:wght@400;500;600&display=swap');

:root{--paper:#F7F4EE;--ink:#10233F;--muted:#5B6B80;--brass:#B8862F;--line:#E4DDCF;--card:#FFFFFF;}

.stApp{
  background-color:#F7F4EE;
  background-image:
    radial-gradient(1200px 500px at 85% -10%, rgba(184,134,47,0.10), transparent 60%),
    repeating-linear-gradient(0deg, rgba(16,35,63,0.035) 0 1px, transparent 1px 56px),
    repeating-linear-gradient(90deg, rgba(16,35,63,0.035) 0 1px, transparent 1px 56px);
}
.stApp, .stApp p, .stApp li, .stApp label, .stApp input, .stApp textarea, .stApp button{
  font-family:'Public Sans',sans-serif;
}
.stApp h1,.stApp h2,.stApp h3{font-family:'Fraunces',serif;color:var(--ink);}
.block-container{max-width:1100px;padding-top:2rem;}
header[data-testid="stHeader"]{background:transparent;}
#MainMenu, footer{visibility:hidden;}
[data-testid="stForm"]{border:0;padding:0;}

.hero{
  position:relative;overflow:hidden;border:1px solid var(--line);border-radius:22px;
  padding:44px 40px 120px;margin:4px 0 18px;
  background:
    url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 1200 120' preserveAspectRatio='none'%3E%3Cg fill='%2310233F' fill-opacity='0.09'%3E%3Crect x='0' y='80' width='50' height='40'/%3E%3Crect x='55' y='60' width='40' height='60'/%3E%3Crect x='100' y='75' width='35' height='45'/%3E%3Crect x='140' y='45' width='45' height='75'/%3E%3Crect x='190' y='70' width='40' height='50'/%3E%3Crect x='235' y='55' width='55' height='65'/%3E%3Crect x='295' y='85' width='30' height='35'/%3E%3Crect x='330' y='35' width='40' height='85'/%3E%3Crect x='375' y='60' width='50' height='60'/%3E%3Crect x='430' y='78' width='35' height='42'/%3E%3Crect x='470' y='50' width='60' height='70'/%3E%3Cpolygon points='540,120 540,62 556,62 556,42 570,42 570,22 577,22 577,2 581,2 581,22 588,22 588,42 602,42 602,62 618,62 618,120'/%3E%3Crect x='630' y='70' width='50' height='50'/%3E%3Crect x='685' y='55' width='40' height='65'/%3E%3Crect x='730' y='80' width='45' height='40'/%3E%3Crect x='780' y='40' width='55' height='80'/%3E%3Crect x='840' y='68' width='35' height='52'/%3E%3Crect x='880' y='50' width='60' height='70'/%3E%3Crect x='945' y='82' width='40' height='38'/%3E%3Crect x='990' y='58' width='50' height='62'/%3E%3Crect x='1045' y='72' width='45' height='48'/%3E%3Crect x='1095' y='45' width='40' height='75'/%3E%3Crect x='1140' y='78' width='60' height='42'/%3E%3C/g%3E%3C/svg%3E") bottom/100% 110px no-repeat,
    linear-gradient(180deg,#FFFFFF 0%,#F4EFE3 100%);
}
.hero .eyebrow{font-size:.78rem;letter-spacing:.14em;text-transform:uppercase;color:var(--brass);font-weight:600;}
.hero h1{font-family:'Fraunces',serif;font-weight:600;font-size:2.8rem;line-height:1.08;margin:6px 0 10px;color:var(--ink);max-width:640px;padding:0;}
.hero p{color:var(--muted);font-size:1.08rem;max-width:560px;margin:0;}

.stTextInput input{border-radius:12px;font-size:1.05rem;padding:14px 16px;border:1px solid var(--line);background:#fff;}
.stTabs [data-baseweb="tab-list"]{gap:6px;border-bottom:1px solid var(--line);}
.stTabs button[data-baseweb="tab"]{font-weight:600;color:var(--muted);}
.stTabs button[aria-selected="true"]{color:var(--ink);}
.stTabs [data-baseweb="tab-highlight"]{background-color:var(--brass);}

.kpi{background:var(--card);border:1px solid var(--line);border-left:4px solid var(--line);border-radius:14px;padding:14px 16px;height:100%;}
.kpi.bad{border-left-color:#B3261E;}
.kpi .k{font-size:.72rem;letter-spacing:.08em;text-transform:uppercase;color:var(--muted);font-weight:600;}
.kpi .v{font-family:'Fraunces',serif;font-size:2.1rem;line-height:1.15;color:var(--ink);}
.kpi .s{font-size:.8rem;color:var(--muted);}

.addr{font-family:'Fraunces',serif;font-size:1.9rem;color:var(--ink);margin:10px 0 0;line-height:1.15;}
.subaddr{color:var(--muted);font-size:.9rem;margin:2px 0 14px;}
.callout{background:#FFFBF2;border:1px solid #EBDDB8;border-radius:14px;padding:14px 18px;color:var(--ink);margin:14px 0;}
.sec{font-family:'Fraunces',serif;font-size:1.35rem;margin:22px 0 8px;color:var(--ink);}

.vcard{background:#fff;border:1px solid var(--line);border-radius:12px;padding:12px 14px;margin-bottom:10px;}
.vtop{display:flex;gap:10px;align-items:center;flex-wrap:wrap;margin-bottom:6px;font-size:.82rem;color:var(--muted);}
.vdesc{font-size:.92rem;color:var(--ink);}
.pill{display:inline-block;padding:2px 10px;border-radius:999px;font-size:.78rem;font-weight:600;}
.pill.c{background:#FBE4E2;color:#8C1D18;}
.pill.b{background:#FCEBD0;color:#8A5200;}
.pill.a{background:#E1EAF6;color:#2C4F82;}
.pill.i{background:#ECEEF1;color:#4B5563;}

.step{background:#fff;border:1px solid var(--line);border-radius:14px;padding:18px;height:100%;}
.step .n{font-family:'Fraunces',serif;font-size:1.6rem;color:var(--brass);}
.step .t{font-weight:600;color:var(--ink);margin:2px 0 4px;}
.step .d{color:var(--muted);font-size:.9rem;}
</style>
""", unsafe_allow_html=True)

# ------------------------------------------------------------ session state
for _k, _v in {
    "candidates": [], "search_error": None, "messages": [], "question_count": 0,
    "pending_question": None, "link_checked": False, "chat_bbl": None, "search_text": "",
}.items():
    st.session_state.setdefault(_k, _v)


def pretty_address(name: str) -> str:
    return (name or "").title()


def plural(n: int, word: str) -> str:
    return f"{n:,} {word}{'' if n == 1 else 's'}"


def run_search(text: str) -> None:
    """Resolve what the user typed to a NYC building, or explain why we can't. Never guesses."""
    text = (text or "").strip()
    st.session_state.search_error = None
    st.session_state.suggestions = []
    if len(text) < 3:
        st.session_state.search_error = "Type a street address, like “219 13th St, Brooklyn”."
        return
    try:
        res = resolve_address(text)
    except LookupFailed:
        st.session_state.search_error = "NYC's address service didn't respond. Please try again in a moment."
        return
    st.session_state.candidates = res.candidates      # only verified matches ever reach the report
    st.session_state.cand_idx = 0
    if res.status in ("ok", "choose"):
        st.query_params["address"] = text
        return
    st.session_state.suggestions = res.suggestions     # "did you mean": needs an explicit click
    st.session_state.search_error = res.message


def accept_suggestion(i: int) -> None:
    c = st.session_state.suggestions[i]
    st.session_state.candidates = [c]
    st.session_state.cand_idx = 0
    st.session_state.suggestions = []
    st.session_state.search_error = None
    st.session_state.search_text = f"{pretty_address(c['name'])}, {c.get('borough') or ''} {c.get('zip') or ''}".strip()
    st.query_params["address"] = st.session_state.search_text


def pick_example(text: str) -> None:
    st.session_state.search_text = text
    run_search(text)


def queue_question(q: str) -> None:
    st.session_state.pending_question = q


@st.cache_data(ttl=3600, show_spinner=False)
def load_report(building_json: str) -> dict:
    return build_report(json.loads(building_json))


# Open a shared link like  ?address=219+13th+St,+Brooklyn  on first load.
if not st.session_state.link_checked:
    st.session_state.link_checked = True
    _addr = st.query_params.get("address")
    if _addr:
        st.session_state.search_text = _addr
        run_search(_addr)

# --------------------------------------------------------------------- hero
st.markdown("""
<div class="hero">
<div class="eyebrow">NYC · HPD violations · 311 complaints</div>
<h1>Know the building before you sign.</h1>
<p>Look up any NYC address and see its real housing-violation history, explained in plain English.</p>
</div>
""", unsafe_allow_html=True)

with st.form("search_form"):
    c_in, c_btn = st.columns([5, 1])
    c_in.text_input(
        "Address", key="search_text", label_visibility="collapsed",
        placeholder="Try “219 13th St, Brooklyn”: street number, street, borough",
    )
    submitted = c_btn.form_submit_button("Check building", type="primary")
if submitted:
    run_search(st.session_state.search_text)

ex_cols = st.columns([1.2, 2, 2, 2])
ex_cols[0].caption("Try an example:")
for col, ex in zip(ex_cols[1:], EXAMPLES):
    col.button(ex, key=f"ex_{ex}", on_click=pick_example, args=(ex,), use_container_width=True)

st.caption(
    "RentGuard reports what NYC's HPD and 311 records say. It can't verify current "
    "conditions and isn't legal advice."
)

if st.session_state.search_error:
    st.warning(st.session_state.search_error)

for _i, _c in enumerate(st.session_state.get("suggestions") or []):
    st.button(
        f"Yes, use {pretty_address(_c['name'])}, {_c.get('neighborhood') or ''} {_c.get('borough') or ''} {_c.get('zip') or ''}",
        key=f"sug_{_i}", on_click=accept_suggestion, args=(_i,),
    )

candidates = st.session_state.candidates
if len(candidates) > 1:
    with st.expander("Not the right building? Pick another match"):
        st.selectbox(
            "Matches", options=list(range(len(candidates))), key="cand_idx",
            format_func=lambda i: (
                f"{pretty_address(candidates[i]['name'])}: "
                f"{candidates[i].get('neighborhood') or ''} {candidates[i].get('borough') or ''} "
                f"{candidates[i].get('zip') or ''}"
            ),
        )

report = None
if candidates:
    idx = min(st.session_state.get("cand_idx", 0), len(candidates) - 1)
    chosen = candidates[idx]
    try:
        with st.spinner("Pulling live records from NYC Open Data…"):
            report = load_report(json.dumps(chosen, sort_keys=True))
    except LookupFailed:
        st.error("NYC Open Data didn't respond. Please try again in a moment.")

if report and st.session_state.chat_bbl != report["building"]["bbl"]:
    st.session_state.chat_bbl = report["building"]["bbl"]
    st.session_state.messages = []

# --------------------------------------------------------------------- tabs
tab_report, tab_chat, tab_toolkit, tab_about = st.tabs(
    ["🏢 Building report", "💬 Ask about this building", "🧰 Tenant toolkit", "ℹ️ About & feedback"]
)


def kpi(label: str, value, sub: str = "", tone: str = "") -> str:
    return (
        f"<div class='kpi {tone}'><div class='k'>{html.escape(label)}</div>"
        f"<div class='v'>{value}</div><div class='s'>{html.escape(sub)}</div></div>"
    )


def violation_card(v: dict) -> str:
    cls = v["class"].lower() if v["class"] in ("A", "B", "C") else "i"
    desc = v["description"]
    desc = html.escape(desc[:240] + ("…" if len(desc) > 240 else ""))
    status = html.escape(v["status_detail"] or v["status"])
    return (
        f"<div class='vcard'><div class='vtop'>"
        f"<span class='pill {cls}'>Class {html.escape(v['class'])}</span>"
        f"<span>Inspected {html.escape(v['date'])}</span><span>· {status}</span></div>"
        f"<div class='vdesc'>{desc}</div></div>"
    )


def headline(s: dict) -> str:
    if s["total"] == 0 and s["complaints_total"] == 0:
        return (
            "No HPD violations or HPD-routed 311 complaints are recorded for this building in NYC Open "
            "Data. That's a good sign, but it isn't proof the building is problem-free. It only means "
            "nothing was recorded here."
        )
    if s["total"] == 0:
        return (
            f"No HPD violations are recorded, but tenants filed {plural(s['complaints_total'], 'HPD-routed 311 complaint')} "
            f"({s['complaints_3y']} in the last 3 years)."
        )
    first_year = (s["first_date"] or "")[:4] or "records began"
    text = f"HPD has recorded {plural(s['total'], 'violation')} here since {first_year}, {s['open']} still open"
    c_open = s["open_by_class"].get("C", 0)
    if c_open:
        text += f" ({c_open} of them Class C, the most serious category)"
    text += (
        f". In the last 12 months: {plural(s['last_12m'], 'new violation')} and "
        f"{plural(s['complaints_12m'], 'HPD-routed 311 complaint')}."
    )
    return text


# --------------------------------------------------------- tab 1: the report
with tab_report:
    if not report:
        st.markdown("<div class='sec'>How it works</div>", unsafe_allow_html=True)
        s1, s2, s3 = st.columns(3)
        s1.markdown(
            "<div class='step'><div class='n'>1</div><div class='t'>Search an address</div>"
            "<div class='d'>We match it to the city's tax-lot ID, so any NYC building works.</div></div>",
            unsafe_allow_html=True)
        s2.markdown(
            "<div class='step'><div class='n'>2</div><div class='t'>Pull live city records</div>"
            "<div class='d'>HPD violations and HPD-routed 311 complaints, straight from NYC Open Data.</div></div>",
            unsafe_allow_html=True)
        s3.markdown(
            "<div class='step'><div class='n'>3</div><div class='t'>Get plain-English answers</div>"
            "<div class='d'>An AI explains the records. It's blocked from legal claims, “all clear” claims, "
            "and made-up addresses.</div></div>",
            unsafe_allow_html=True)
    else:
        b, s = report["building"], report["stats"]
        where = ", ".join(p for p in (b.get("neighborhood"), b.get("borough")) if p)
        st.markdown(f"<div class='addr'>{html.escape(pretty_address(b['name']))}</div>", unsafe_allow_html=True)
        st.markdown(
            f"<div class='subaddr'>{html.escape(where)} {html.escape(b.get('zip') or '')} · BBL {b['bbl']} · "
            f"live data pulled {report['fetched_at'].replace('T', ' ')} UTC</div>",
            unsafe_allow_html=True)

        oc = s["open_by_class"]
        first_year = (s["first_date"] or "")[:4] or "n/a"
        k = st.columns(5)
        k[0].markdown(kpi("Open violations", s["open"], "right now", "bad" if s["open"] else ""), unsafe_allow_html=True)
        k[1].markdown(kpi("Open Class C", oc.get("C", 0), "immediately hazardous", "bad" if oc.get("C", 0) else ""), unsafe_allow_html=True)
        k[2].markdown(kpi("Last 12 months", s["last_12m"], "new violations"), unsafe_allow_html=True)
        k[3].markdown(kpi("All time", s["total"], f"since {first_year}"), unsafe_allow_html=True)
        k[4].markdown(kpi("311 complaints", s["complaints_3y"], "HPD-routed, last 3 yrs"), unsafe_allow_html=True)

        st.markdown(f"<div class='callout'>{html.escape(headline(s))}</div>", unsafe_allow_html=True)
        if report["truncated"]:
            st.caption("This building has a very large record count; only the most recent 5,000 rows of each type are shown.")

        left, right = st.columns([3, 2])
        with left:
            st.markdown("<div class='sec'>Needs attention</div>", unsafe_allow_html=True)
            open_v = sorted(
                (v for v in report["violations"] if v["status"] == "Open"),
                key=lambda v: (CLASS_RANK.get(v["class"], 9), -int(v["date"].replace("-", "") or 0)),
            )[:5]
            if open_v:
                st.markdown("".join(violation_card(v) for v in open_v), unsafe_allow_html=True)
                st.caption("Most serious open violations first. Class C is immediately hazardous.")
            else:
                st.info("No open violations are on record for this building.")
        with right:
            st.markdown("<div class='sec'>Location</div>", unsafe_allow_html=True)
            if b.get("lat") and b.get("lon"):
                pt = pd.DataFrame({"lat": [b["lat"]], "lon": [b["lon"]]})
                try:
                    st.map(pt, zoom=15, size=25, color="#B8862F")
                except TypeError:
                    st.map(pt)

        c1, c2 = st.columns(2)
        with c1:
            st.markdown("<div class='sec'>Violations by year</div>", unsafe_allow_html=True)
            per_year = s["per_year"]
            if per_year:
                years = sorted(per_year)
                classes = sorted({c for y in per_year.values() for c in y})
                chart = pd.DataFrame(
                    {c: [per_year[y].get(c, 0) for y in years] for c in classes}, index=years)
                st.bar_chart(chart, color=[CLASS_COLORS.get(c, "#888888") for c in chart.columns])
            else:
                st.caption("No violations on record.")
        with c2:
            st.markdown("<div class='sec'>What tenants reported (3 yrs)</div>", unsafe_allow_html=True)
            types = pd.Series(s["complaint_types_3y"]).sort_values(ascending=False).head(6)
            if len(types):
                st.bar_chart(types, color="#B8862F")
            else:
                st.caption("No HPD-routed 311 complaints in the last 3 years.")

        st.markdown("<div class='sec'>All violations</div>", unsafe_allow_html=True)
        if report["violations"]:
            df = pd.DataFrame(report["violations"])
            f1, f2 = st.columns(2)
            status_pick = f1.selectbox("Status", ["All", "Open", "Closed"])
            all_classes = sorted(df["class"].unique())
            class_pick = f2.multiselect("Class", all_classes, default=all_classes)
            view = df[df["class"].isin(class_pick)]
            if status_pick != "All":
                view = view[view["status"] == status_pick]
            st.dataframe(
                view[["date", "class", "status", "description"]].rename(columns={
                    "date": "Inspected", "class": "Class", "status": "Status",
                    "description": "What HPD cited"}),
                hide_index=True, height=360,
            )
        else:
            st.caption("No violations on record.")

        with st.expander("How to read violation classes"):
            st.markdown(
                "- **Class A:** non-hazardous.\n"
                "- **Class B:** hazardous.\n"
                "- **Class C:** immediately hazardous (for example, no heat or an infestation).\n\n"
                "“Open” means HPD hasn't recorded the violation as corrected or dismissed. Records come from "
                "the city's data and cover the whole tax lot."
            )
        st.caption("Source: NYC HPD Housing Maintenance Code Violations and 311 Service Requests via NYC Open Data. "
                   "Share this report by copying the page URL.")

# ---------------------------------------------------------- tab 2: AI chat
with tab_chat:
    if not report:
        st.info("Look up a building first, then ask follow-up questions about its records here.")
    else:
        b = report["building"]
        st.markdown(
            f"Asking about **{html.escape(pretty_address(b['name']))}**. Answers use only this "
            "building's live records.")
        remaining = MAX_QUESTIONS_PER_SESSION - st.session_state.question_count
        cols = st.columns(len(CHAT_SUGGESTIONS))
        for i, (col, q) in enumerate(zip(cols, CHAT_SUGGESTIONS)):
            col.button(q, key=f"sugg_{i}", on_click=queue_question, args=(q,),
                       disabled=remaining <= 0, use_container_width=True)

        for m in st.session_state.messages:
            with st.chat_message(m["role"]):
                st.markdown(m["content"])
                if m["role"] == "assistant":
                    if m.get("verified"):
                        st.caption("✓ Checked against this building's records for legal claims, "
                                   "“all clear” claims, and citations.")
                    else:
                        st.caption("Showing raw records because the AI answer didn't pass accuracy checks.")
                    if m.get("notes"):
                        with st.expander("How this answer was checked"):
                            st.caption(", ".join(m["notes"]))

        if remaining <= 0:
            st.info("You've used all questions for this session. Refresh the page to start a new one.")
        else:
            typed = st.chat_input("Ask about this building…")
            question = typed or st.session_state.pop("pending_question", None)
            if question:
                try:
                    with st.spinner("Checking the records…"):
                        result = answer_question(question, report)
                except Exception:
                    st.error("The AI service is unavailable right now. Please try again in a moment.")
                else:
                    st.session_state.question_count += 1
                    st.session_state.messages.append({"role": "user", "content": question})
                    st.session_state.messages.append({
                        "role": "assistant", "content": result["answer"],
                        "verified": result["verified"], "notes": result["notes"]})
                    st.rerun()
            st.caption(f"{remaining} question{'s' if remaining != 1 else ''} left this session.")

# --------------------------------------------------------- tab 3: toolkit
with tab_toolkit:
    st.markdown("<div class='sec'>Before you sign: a touring checklist</div>", unsafe_allow_html=True)
    with st.expander("In the apartment", expanded=True):
        st.markdown(
            "- Run the hot water and check the radiators or vents. NYC heat season runs Oct 1 to May 31; "
            "ask how heat has been in past winters.\n"
            "- Look for water stains, peeling paint, or musty smells on ceilings and corners.\n"
            "- Check under sinks and behind appliances for droppings, glue traps, or sealed gaps.\n"
            "- Test window locks and seals, and look for working smoke and CO detectors.")
    with st.expander("Ask the landlord or broker"):
        st.markdown(
            "- Are there any open HPD violations? Have there been recent heat or hot-water outages?\n"
            "- Ask to see the bed bug history disclosure that comes with a NYC lease.\n"
            "- Who is the owner or managing agent, and how are repair requests handled?")
    with st.expander("Do your own homework"):
        st.markdown(
            "- Run the building through the report above, then compare it with HPD Online.\n"
            "- Look up who owns the building and their other properties with Who Owns What (link below).")

    st.markdown("<div class='sec'>Real help beyond this tool</div>", unsafe_allow_html=True)
    st.markdown("""
- **[NYC 311](https://portal.311.nyc.gov/)**: file a new complaint about heat, pests, mold, and more.
- **[HPD Online](https://hpdonline.hpdnyc.org/)**: the city's own building lookup.
- **[Who Owns What (JustFix)](https://whoownswhat.justfix.org/)**: see a landlord's wider portfolio.
- **[Housing Court Answers](https://housingcourtanswers.org/)**: free help with housing court and tenant rights.
- **[Met Council on Housing](https://www.metcouncilonhousing.org/)**: tenant rights hotline and counseling.
- **[NYC Tenant Resource Portal](https://www.nyc.gov/site/tenantresourceportal/index.page)**: the city's tenant-rights guide.
""")

# -------------------------------------------------------- tab 4: about
with tab_about:
    st.markdown("<div class='sec'>Why this exists</div>", unsafe_allow_html=True)
    st.markdown(
        "I built RentGuard while house hunting in NYC. City violation records are public but hard to "
        "read, and I wanted plain-English answers I could trust.")
    st.markdown("<div class='sec'>How it works</div>", unsafe_allow_html=True)
    st.markdown(
        "1. Your address is matched to the city's tax-lot ID (BBL) using NYC Planning Labs' Geosearch.\n"
        "2. Live HPD violations and HPD-routed 311 complaints for that lot are pulled from NYC Open Data.\n"
        "3. An AI model answers questions using only those records. Automated checks block legal claims, "
        "“no issues” claims, and made-up addresses, and require citations. If an answer fails twice, "
        "you see raw records instead of a guess.")
    st.markdown("<div class='sec'>What it can't tell you</div>", unsafe_allow_html=True)
    st.markdown(
        "- It only knows what was reported to the city. No records doesn't mean no problems.\n"
        "- It doesn't verify current conditions, rent, or the landlord's behavior.\n"
        "- Records cover the whole tax lot, which can include more than one building.\n"
        "- It isn't legal advice.")
    st.markdown(
        "**Built by** [Aishwarya M Y](https://aishwaryamy.github.io/) · "
        "[Source code on GitHub](https://github.com/aishwaryamy/RentGuard)")

    st.markdown("<div class='sec'>Tell me what you think</div>", unsafe_allow_html=True)
    with st.form("feedback_form", clear_on_submit=True):
        feedback_text = st.text_area("What worked, what didn't, or what's missing?")
        feedback_email = st.text_input("Email (optional, if you'd like a reply)")
        sent = st.form_submit_button("Send feedback")
        if sent and feedback_text.strip():
            FEEDBACK_PATH.parent.mkdir(parents=True, exist_ok=True)
            is_new = not FEEDBACK_PATH.exists()
            with open(FEEDBACK_PATH, "a", newline="") as f:
                w = csv.writer(f)
                if is_new:
                    w.writerow(["timestamp", "feedback", "email"])
                w.writerow([datetime.now(timezone.utc).isoformat(), feedback_text.strip(), feedback_email.strip()])
            st.success("Thanks, this was saved.")
        elif sent:
            st.warning("Add a bit of feedback text before sending.")
    st.caption(f"Prefer email? {FEEDBACK_EMAIL}")
