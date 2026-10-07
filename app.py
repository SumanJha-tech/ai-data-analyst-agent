import logging

import streamlit as st
from ask import (
    ask_question, validate_result, auto_chart, generate_insight, con,
    detect_anomalies, load_uploaded_file, list_tables, DEFAULT_TABLES, MODEL
)
from gemini_client import (
    GeminiError, GeminiUnavailable, GeminiNotConfigured, check_ai_status,
    REQUEST_FAILED_MESSAGE
)
from demo_mode import (
    find_demo_answer, suggest_questions, demo_result_frame, demo_chart, DEMO_BADGE
)

logger = logging.getLogger(__name__)

st.set_page_config(
    page_title="AI Data Analyst Agent",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Every question the AI can realistically answer about the built-in Olist
# dataset, grouped by topic, shown in the dropdown.
QUESTION_BANK = {
    "💰 Revenue & Sales": [
        "What is the total revenue from all orders?",
        "Which product category had the highest total revenue?",
        "What are the top 5 product categories by total revenue?",
        "What are the bottom 5 product categories by total revenue?",
        "What is the average order value?",
        "What is the average price per product category?",
        "Which product category has the most orders?",
        "Which 10 products generated the most revenue?",
        "Which single product has the highest price?",
        "What is the monthly revenue trend over time?",
        "What is the total number of order items sold?",
    ],
    "🚚 Delivery & Logistics": [
        "How many orders were delivered late?",
        "What is the average delivery time in days?",
        "Which state has the most delayed deliveries?",
        "What is the average freight value per order?",
        "What is the total freight cost across all orders?",
        "Which product category has the highest average freight cost?",
        "What percentage of orders were delivered before the estimated date?",
        "What is the average time between order approval and delivery to the carrier?",
        "Which state has the fastest average delivery time?",
    ],
    "👥 Customers & Geography": [
        "How many unique customers are there?",
        "Which state has the most customers?",
        "Which city has the highest number of orders?",
        "What are the top 10 states by number of customers?",
        "Which state generates the highest average order value?",
        "How many customers are there per city, for the top 10 cities?",
    ],
    "💳 Payments": [
        "What is the most common payment type?",
        "What is the average payment value?",
        "How many orders used more than one payment installment?",
        "What is the average number of payment installments?",
        "What percentage of orders were paid by credit card?",
        "What is the highest number of installments used for a single order?",
        "What is the total payment value collected across all orders?",
    ],
    "⭐ Reviews & Satisfaction": [
        "What is the average review score?",
        "How many orders have a review score of 5?",
        "How many orders have a review score of 1 or 2?",
        "Which product category has the lowest average review score?",
        "Which product category has the highest average review score?",
        "Is there a relationship between delivery delay and review score?",
        "How many reviews include a written comment?",
        "What percentage of orders received a review at all?",
    ],
    "📦 Orders Overview": [
        "How many orders are there in total?",
        "What percentage of orders were cancelled?",
        "How many orders are still processing or shipped, not yet delivered?",
        "How many orders fall into each order status?",
        "What is the busiest day of the week for orders?",
    ],
    "🏷️ Products & Sellers": [
        "How many unique products are there?",
        "How many unique sellers are there?",
        "Which seller has sold the most items?",
        "What is the average weight of products, in kilograms?",
        "Which product category has the heaviest average product weight?",
        "What is the average number of photos per product listing?",
        "How many product categories are there in total?",
    ],
}
HEADER_PREFIX = "──"

def build_dropdown_options():
    options = ["-- Select a question --"]
    for category, questions in QUESTION_BANK.items():
        options.append(f"{HEADER_PREFIX} {category} {HEADER_PREFIX}")
        options.extend(questions)
    return options

defaults = {
    "chat_history": [],
    "active_tables": list(DEFAULT_TABLES),
    "uploaded_tables": [],
    "anomaly_results": None,
    "page": "🏠 Dashboard",
    "pending_question": None,
}
for key, value in defaults.items():
    if key not in st.session_state:
        st.session_state[key] = value


# Streamlit forbids changing a widget-bound session_state key (like "page")
# except from inside that widget's own on_click/on_change callback — so
# every navigation action below goes through a callback.
def go_to_chat_with(question):
    st.session_state["pending_question"] = question
    st.session_state["page"] = "💬 Chat Analyst"


def pick_from_dropdown():
    picked = st.session_state["dropdown_pick"]
    if picked and not picked.startswith(HEADER_PREFIX) and picked != "-- Select a question --":
        go_to_chat_with(picked)


def clear_chat():
    st.session_state["chat_history"] = []


def demo_scope_ok():
    """Saved demo answers are about the Olist tables, so only offer them while those are in scope."""
    return set(DEFAULT_TABLES).issubset(st.session_state["active_tables"])


def process_question(question):
    history = [{"question": t["question"], "sql": t["sql"]} for t in st.session_state["chat_history"]]
    turn = {
        "question": question, "sql": None, "df": None, "valid": False, "reason": None,
        "insight": None, "fig": None, "error": None, "demo": False, "suggestions": [],
    }
    can_demo = demo_scope_ok()
    try:
        sql, df = ask_question(question, history=history, table_filter=st.session_state["active_tables"])
        is_valid, reason = validate_result(df)
        try:
            insight = generate_insight(question, df, history=history)
        except GeminiError as e:
            logger.warning("Insight unavailable: %s", e.technical_detail)
            insight = None  # the query result is still real; only the AI write-up is missing
        turn.update(sql=sql, df=df, valid=is_valid, reason=reason, insight=insight, fig=auto_chart(df))
    except (GeminiUnavailable, GeminiNotConfigured) as e:
        entry = find_demo_answer(question) if can_demo else None
        if entry:
            df = demo_result_frame(entry)
            is_valid, reason = validate_result(df)
            turn.update(sql=entry["sql"], df=df, valid=is_valid, reason=reason,
                        insight=entry["insight"], fig=demo_chart(df, entry["chart_type"]), demo=True)
        else:
            turn.update(error=str(e), suggestions=suggest_questions(4, exclude=question) if can_demo else [])
    except GeminiError as e:
        turn.update(error=str(e), suggestions=suggest_questions(4, exclude=question) if can_demo else [])
    except Exception:
        logger.exception("Could not answer question")
        turn.update(error=REQUEST_FAILED_MESSAGE, suggestions=suggest_questions(4, exclude=question) if can_demo else [])
    st.session_state["chat_history"].append(turn)


# One tiny live check at most every 60s (shared across sessions), not on every rerun.
@st.cache_data(ttl=60, show_spinner=False)
def get_ai_status():
    return check_ai_status(MODEL)


@st.cache_data
def load_kpis():
    total_orders = con.execute("SELECT COALESCE(COUNT(*), 0) FROM orders").fetchone()[0]
    total_revenue = con.execute("SELECT COALESCE(SUM(payment_value), 0) FROM payments").fetchone()[0]
    avg_review = con.execute("SELECT COALESCE(AVG(review_score), 0) FROM reviews").fetchone()[0]
    total_customers = con.execute("SELECT COALESCE(COUNT(DISTINCT customer_id), 0) FROM customers").fetchone()[0]
    return total_orders, total_revenue, avg_review, total_customers

total_orders, total_revenue, avg_review, total_customers = load_kpis()
all_tables = list_tables(con)

st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap');

    :root {
        --bg: #0e1116; --surface: #151a21; --surface-2: #1a212b; --border: #262d38;
        --text: #e6e9ef; --muted: #8b95a5; --faint: #6b7585;
        --accent: #3b82f6; --accent-text: #6ea8fe;
        --green: #34d399; --amber: #f5a524; --red: #f87171;
    }

    html, body, [class*="css"] { font-family: 'Inter', sans-serif; }
    .stApp { background: var(--bg); }
    #MainMenu, footer, header {visibility: hidden;}
    .block-container { padding-top: 1.6rem; padding-bottom: 2rem; max-width: 1180px; }
    div[data-testid="stVerticalBlock"] { gap: 0.85rem; }
    div[data-testid="stVerticalBlockBorderWrapper"] { background: var(--surface); border-radius: 10px; }

    ::-webkit-scrollbar { width: 8px; height: 8px; }
    ::-webkit-scrollbar-thumb { background: #2b3441; border-radius: 8px; }

    /* ---- Sidebar ---- */
    section[data-testid="stSidebar"] { background: #0b0e13; border-right: 1px solid var(--border); }
    .brand-row { display:flex; align-items:center; gap:0.6rem; padding: 0.4rem 0 0.1rem 0; }
    .brand-mark {
        width: 32px; height: 32px; border-radius: 8px; background: var(--accent); color: #fff;
        display:flex; align-items:center; justify-content:center;
        font-size: 0.8rem; font-weight: 700; letter-spacing: 0.02em;
    }
    .sidebar-brand { font-size: 1.05rem; font-weight: 650; color: var(--text); letter-spacing: -0.01em; }
    .sidebar-sub { color: var(--faint); font-size:0.68rem; letter-spacing:0.09em; margin: 0 0 1.1rem 2.7rem; font-weight: 500; }
    .ai-badge {
        display: inline-flex; align-items: center; gap: 0.5rem;
        background: rgba(52,211,153,0.08); color: var(--green);
        font-size: 0.76rem; font-weight: 500;
        padding: 0.32rem 0.7rem; border-radius: 6px;
        margin-bottom: 1.3rem; border: 1px solid rgba(52,211,153,0.22);
    }
    .ai-badge.warn { background: rgba(245,165,36,0.08); color: var(--amber); border-color: rgba(245,165,36,0.26); }
    .pulse-dot { width: 6px; height: 6px; background: var(--green); border-radius: 50%; }
    .ai-badge.warn .pulse-dot { background: var(--amber); }
    .scope-pill {
        display:inline-block; background: var(--surface-2); color: #b4bdcb;
        border: 1px solid var(--border); border-radius: 6px;
        padding: 0.16rem 0.55rem; font-size: 0.7rem; font-weight: 500;
        margin: 0.15rem 0.25rem 0.15rem 0;
    }

    /* ---- Nav radio as sidebar list ---- */
    section[data-testid="stSidebar"] div[role="radiogroup"] label {
        background: transparent; color: var(--muted); border-radius: 8px;
        padding: 0.5rem 0.75rem; margin-bottom: 0.15rem; font-weight: 500; width: 100%;
        transition: background 0.12s ease, color 0.12s ease;
    }
    section[data-testid="stSidebar"] div[role="radiogroup"] label:hover { background: var(--surface); color: var(--text); }
    section[data-testid="stSidebar"] div[role="radiogroup"] label:has(input:checked) {
        background: var(--surface-2); color: var(--text);
    }

    /* ---- Page title ---- */
    .page-title { font-size: 1.75rem; font-weight: 650; color: var(--text); letter-spacing: -0.02em; margin-bottom: 0.2rem; }
    .page-subtitle { color: var(--muted); font-size: 0.93rem; margin-bottom: 0.4rem; max-width: 72ch; }

    /* ---- Cards ---- */
    .kpi-card, .section-card {
        background: var(--surface); border-radius: 10px; border: 1px solid var(--border);
    }
    .kpi-card { padding: 1.1rem 1.25rem; }
    .kpi-label { color: var(--muted); font-size: 0.74rem; font-weight: 500; text-transform: uppercase; letter-spacing: 0.07em; }
    .kpi-value { color: var(--text); font-size: 1.7rem; font-weight: 650; margin-top: 0.3rem; letter-spacing: -0.02em; font-variant-numeric: tabular-nums; }
    .kpi-icon { display: none; }

    .section-card { padding: 1.1rem 1.3rem; }
    .section-title {
        color: var(--muted); font-size: 0.72rem; font-weight: 600;
        text-transform: uppercase; letter-spacing: 0.09em; margin: 0 0 0.4rem 0;
    }
    .section-card .section-title { margin-bottom: 0.6rem; }
    .kpi-card { min-height: 5.6rem; }

    /* ---- Inputs ---- */
    .stTextInput>div>div>input, .stChatInput textarea, .stSelectbox>div>div {
        background-color: var(--surface) !important; color: var(--text) !important;
        border: 1px solid var(--border) !important; border-radius: 8px !important;
    }
    .stTextInput>div>div>input:focus { border-color: var(--accent) !important; box-shadow: 0 0 0 3px rgba(59,130,246,0.18) !important; }

    /* ---- Buttons ---- */
    .stButton>button { border-radius: 8px; font-weight: 500; transition: background 0.12s ease, border-color 0.12s ease; }
    div[data-testid="stButton"] button[kind="primary"] {
        background: var(--accent); color: #fff; border: 1px solid var(--accent); padding: 0.55rem 1.4rem;
    }
    div[data-testid="stButton"] button[kind="primary"]:hover { background: #2f6fe0; border-color: #2f6fe0; }
    div[data-testid="stButton"] button[kind="secondary"] {
        background: var(--surface); color: #cbd2dc; border: 1px solid var(--border);
        padding: 0.45rem 0.9rem; font-size: 0.84rem; text-align: left; box-shadow: none;
    }
    div[data-testid="stButton"] button[kind="secondary"]:hover { background: var(--surface-2); border-color: #3a4556; color: #fff; }

    /* ---- Insight / anomaly boxes ---- */
    .insight-box {
        background: var(--surface); border: 1px solid var(--border); border-left: 3px solid var(--accent);
        padding: 1rem 1.25rem; border-radius: 8px; color: #cdd3dd; line-height: 1.65;
    }
    .anomaly-box {
        background: var(--surface); border: 1px solid var(--border); border-left: 3px solid var(--amber);
        padding: 1rem 1.25rem; border-radius: 8px; color: #cdd3dd; line-height: 1.65;
    }
    .stat-chip {
        display:inline-block; background: var(--surface); border:1px solid var(--border); border-radius: 6px;
        padding: 0.45rem 0.75rem; margin: 0.2rem 0.3rem 0.2rem 0; font-size: 0.8rem; color: var(--muted);
    }
    .stat-chip b { color: var(--text); font-weight: 600; }

    .status-ok { color: var(--green); font-weight: 500; font-size: 0.88rem; }
    .status-warn { color: var(--amber); font-weight: 500; font-size: 0.88rem; }
    .status-err { color: var(--red); font-weight: 500; font-size: 0.88rem; }
    .demo-badge {
        display: inline-block; background: rgba(245,165,36,0.08); color: var(--amber);
        border: 1px solid rgba(245,165,36,0.26); border-radius: 6px;
        padding: 0.14rem 0.6rem; font-size: 0.72rem; font-weight: 500; margin-bottom: 0.5rem;
    }

    /* ---- Chat bubbles ---- */
    div[data-testid="stChatMessage"] {
        background: var(--surface); border: 1px solid var(--border); border-radius: 10px;
    }
    code, .stCode { font-family: 'JetBrains Mono', monospace !important; }

    /* ---- Overview page tables ---- */
    .overview-table { width:100%; border-collapse: collapse; font-size: 0.88rem; }
    .overview-table th { text-align:left; color: var(--muted); font-size:0.72rem; text-transform:uppercase; font-weight: 600;
        letter-spacing:0.07em; padding: 0.5rem 0.7rem; border-bottom: 1px solid var(--border); }
    .overview-table td { padding: 0.6rem 0.7rem; border-bottom: 1px solid #1d242e; color: #c3cad6; vertical-align: top; }
    .overview-table td b { color: var(--text); font-weight: 600; }
</style>
""", unsafe_allow_html=True)

with st.sidebar:
    st.markdown('<div class="brand-row"><div class="brand-mark">DA</div><span class="sidebar-brand">AI Data Analyst</span></div>', unsafe_allow_html=True)
    st.markdown('<p class="sidebar-sub">TEXT-TO-SQL · GEMINI-POWERED</p>', unsafe_allow_html=True)
    ai_status = get_ai_status()
    if ai_status == "ready":
        st.markdown('<div class="ai-badge"><span class="pulse-dot"></span> Gemini AI Ready</div>', unsafe_allow_html=True)
    else:
        badge_text = "AI not configured, demo mode" if ai_status == "not_configured" else "AI busy, demo mode"
        st.markdown(f'<div class="ai-badge warn"><span class="pulse-dot"></span> {badge_text}</div>', unsafe_allow_html=True)

    st.radio(
        "Navigate",
        options=["🏠 Dashboard", "💬 Chat Analyst", "🔍 Anomaly Radar", "📁 My Data", "📖 Dataset Overview"],
        key="page",
        label_visibility="collapsed",
    )

    st.markdown("---")
    st.markdown('<p class="sidebar-sub" style="margin-left:0;">DATASET SCOPE</p>', unsafe_allow_html=True)
    scope_html = "".join(f'<span class="scope-pill">{t}</span>' for t in st.session_state["active_tables"])
    st.markdown(scope_html or '<span class="scope-pill">none selected</span>', unsafe_allow_html=True)
    st.caption(f"{len(all_tables)} table(s) total in database · manage scope on the My Data page")

if st.session_state["page"] == "🏠 Dashboard":
    st.markdown('<p class="page-title">Dashboard</p>', unsafe_allow_html=True)
    st.markdown('<p class="page-subtitle">Live snapshot of the Olist e-commerce dataset — ask anything, in plain English, over on the Chat Analyst page.</p>', unsafe_allow_html=True)

    k1, k2, k3, k4 = st.columns(4)
    with k1:
        st.markdown(f'<div class="kpi-card"><div class="kpi-icon">📦</div><div class="kpi-label">Total Orders</div><div class="kpi-value">{total_orders:,}</div></div>', unsafe_allow_html=True)
    with k2:
        st.markdown(f'<div class="kpi-card"><div class="kpi-icon">💰</div><div class="kpi-label">Total Revenue</div><div class="kpi-value">R$ {total_revenue/1_000_000:.1f}M</div></div>', unsafe_allow_html=True)
    with k3:
        st.markdown(f'<div class="kpi-card"><div class="kpi-icon">⭐</div><div class="kpi-label">Avg Review Score</div><div class="kpi-value">{avg_review:.2f} / 5</div></div>', unsafe_allow_html=True)
    with k4:
        st.markdown(f'<div class="kpi-card"><div class="kpi-icon">👥</div><div class="kpi-label">Total Customers</div><div class="kpi-value">{total_customers:,}</div></div>', unsafe_allow_html=True)

    with st.container(border=True):
        st.markdown('<p class="section-title">Try one of these</p>', unsafe_allow_html=True)
        examples = [
            "Which product category had the highest total revenue?",
            "What is the average delivery time in days?",
            "Which state has the most delayed deliveries?",
            "What is the most common payment type?",
            "How many orders have a review score of 1 or 2?",
            "What are the top 5 product categories by total revenue?",
        ]
        cols = st.columns(3)
        for i, q in enumerate(examples):
            with cols[i % 3]:
                st.button(q, key=f"ex_{i}", width='stretch', on_click=go_to_chat_with, args=(q,))

    with st.container(border=True):
        st.markdown('<p class="section-title">Or browse every question you can ask</p>', unsafe_allow_html=True)
        st.caption("Not sure what to ask? Every question the AI can reliably answer about this dataset is listed here, grouped by topic.")
        st.selectbox(
            "Pick any question",
            options=build_dropdown_options(),
            key="dropdown_pick",
            on_change=pick_from_dropdown,
            label_visibility="collapsed",
        )

    if st.session_state["chat_history"]:
        with st.container(border=True):
            st.markdown('<p class="section-title">Recent conversation</p>', unsafe_allow_html=True)
            for turn in st.session_state["chat_history"][-3:]:
                st.markdown(f"**Q:** {turn['question']}")
                if turn.get("insight"):
                    st.markdown(f'<div class="insight-box" style="margin-bottom:0.4rem;">{turn["insight"]}</div>', unsafe_allow_html=True)

elif st.session_state["page"] == "💬 Chat Analyst":
    st.markdown('<p class="page-title">Chat Analyst</p>', unsafe_allow_html=True)
    st.markdown('<p class="page-subtitle">Ask a question, then ask a follow-up — the AI remembers the conversation, like a real analyst.</p>', unsafe_allow_html=True)

    top1, top2 = st.columns([5, 1])
    with top2:
        st.button("🗑️ Clear chat", width='stretch', on_click=clear_chat)

    st.selectbox(
        "Or pick a question from the full list",
        options=build_dropdown_options(),
        key="dropdown_pick",
        on_change=pick_from_dropdown,
        label_visibility="visible",
        placeholder="Browse every question you can ask...",
    )

    if st.session_state["pending_question"]:
        q = st.session_state["pending_question"]
        st.session_state["pending_question"] = None
        with st.spinner("Thinking..."):
            process_question(q)

    if not st.session_state["chat_history"]:
        st.info("No conversation yet — ask a question below to get started.")

    for turn_idx, turn in enumerate(st.session_state["chat_history"]):
        with st.chat_message("user"):
            st.markdown(turn["question"])
        with st.chat_message("assistant", avatar="📊"):
            if turn["error"]:
                st.markdown(f'<p class="status-warn">⚠ {turn["error"]}</p>', unsafe_allow_html=True)
                for i, suggestion in enumerate(turn.get("suggestions", [])):
                    st.button(suggestion, key=f"sug_{turn_idx}_{i}", on_click=go_to_chat_with, args=(suggestion,))
                continue

            if turn.get("demo"):
                st.markdown(f'<span class="demo-badge">{DEMO_BADGE}</span>', unsafe_allow_html=True)

            if turn["valid"]:
                st.markdown(f'<p class="status-ok">✓ {turn["reason"]}</p>', unsafe_allow_html=True)
            else:
                st.markdown(f'<p class="status-warn">⚠ {turn["reason"]}</p>', unsafe_allow_html=True)

            with st.expander("Generated SQL"):
                st.code(turn["sql"], language="sql")

            c1, c2 = st.columns(2)
            with c1:
                st.dataframe(turn["df"], width='stretch', height=260)
            with c2:
                if turn["fig"] is not None:
                    fig = turn["fig"]
                    fig.update_layout(
                        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                        font_color="#aab3c2", margin=dict(l=10, r=10, t=10, b=10),
                        height=260,
                    )
                    st.plotly_chart(fig, width='stretch')
                else:
                    st.info("No chart available for this result shape.")

            if turn["insight"]:
                st.markdown(f'<div class="insight-box">{turn["insight"]}</div>', unsafe_allow_html=True)
            else:
                st.caption("The AI summary isn't available right now, but the data above is live.")

    question = st.chat_input("Ask a question about the data...")
    if question:
        with st.spinner("Thinking..."):
            process_question(question)
        st.rerun()

elif st.session_state["page"] == "🔍 Anomaly Radar":
    st.markdown('<p class="page-title">Anomaly Radar</p>', unsafe_allow_html=True)
    st.markdown('<p class="page-subtitle">Proactively scans the in-scope tables for statistically unusual values — no question needed.</p>', unsafe_allow_html=True)

    st.markdown(
        '<div class="section-card">'
        '<p class="section-title">What is this page?</p>'
        '<p style="color:#b4bdcb; line-height:1.6;">In simple words: click the button below and the AI '
        "will check every number in your data on its own — no question needed. It looks for values that "
        "stand out as unusually high or low (for example, a shipping cost that is 10x higher than normal), "
        "then explains in plain English which of these are worth your attention.</p>"
        '</div>',
        unsafe_allow_html=True
    )

    if st.button("🔍 Scan for anomalies", type="primary"):
        with st.spinner("Scanning dataset for unusual patterns..."):
            findings, narrative = detect_anomalies(con, st.session_state["active_tables"])
            st.session_state["anomaly_results"] = (findings, narrative)

    if st.session_state["anomaly_results"]:
        findings, narrative = st.session_state["anomaly_results"]

        st.markdown('<div class="anomaly-box">' + narrative.replace("\n", "<br>") + '</div>', unsafe_allow_html=True)

        if findings:
            with st.container(border=True):
                st.markdown('<p class="section-title">Raw statistical findings</p>', unsafe_allow_html=True)
                for f in findings:
                    st.markdown(
                        f'<span class="stat-chip"><b>{f["table"]}.{f["column"]}</b> — '
                        f'{f["outlier_count"]} outliers ({f["pct_of_sample"]}%), '
                        f'mean <b>{f["mean"]:.1f}</b>, extreme value <b>{f["max_outlier"]:.1f}</b></span>',
                        unsafe_allow_html=True
                    )
    else:
        st.info("Click **Scan for anomalies** to run the check.")

elif st.session_state["page"] == "📁 My Data":
    st.markdown('<p class="page-title">My Data</p>', unsafe_allow_html=True)
    st.markdown('<p class="page-subtitle">Upload your own CSV or Excel file and the AI can start answering questions about it immediately.</p>', unsafe_allow_html=True)

    with st.container(border=True):
        st.markdown('<p class="section-title">Upload a dataset</p>', unsafe_allow_html=True)
        uploaded = st.file_uploader("Upload CSV or Excel", type=["csv", "xlsx", "xls"], label_visibility="collapsed")
        if uploaded is not None:
            already = uploaded.name in [u["filename"] for u in st.session_state["uploaded_tables"]]
            if not already:
                try:
                    table_name, row_count, cols = load_uploaded_file(uploaded, con)
                    st.session_state["uploaded_tables"].append({"filename": uploaded.name, "table": table_name, "rows": row_count})
                    if table_name not in st.session_state["active_tables"]:
                        st.session_state["active_tables"].append(table_name)
                    st.success(f"Loaded **{uploaded.name}** as table `{table_name}` ({row_count:,} rows, {len(cols)} columns) — added to the AI's scope.")
                except Exception as e:
                    st.error(f"Could not load file: {e}")

    with st.container(border=True):
        st.markdown('<p class="section-title">Dataset scope — which tables can the AI see?</p>', unsafe_allow_html=True)
        st.caption("Narrow this down (e.g. deselect the Olist tables) to make the AI answer only from your uploaded data.")

        current_tables = list_tables(con)
        for t in current_tables:
            checked = t in st.session_state["active_tables"]
            new_val = st.checkbox(t, value=checked, key=f"scope_{t}")
            if new_val and t not in st.session_state["active_tables"]:
                st.session_state["active_tables"].append(t)
            elif not new_val and t in st.session_state["active_tables"]:
                st.session_state["active_tables"].remove(t)

    if st.session_state["uploaded_tables"]:
        with st.container(border=True):
            st.markdown('<p class="section-title">Your uploaded tables</p>', unsafe_allow_html=True)
            for u in st.session_state["uploaded_tables"]:
                st.markdown(f'<span class="stat-chip"><b>{u["table"]}</b> — from {u["filename"]}, {u["rows"]:,} rows</span>', unsafe_allow_html=True)
                with st.expander(f"Preview {u['table']}"):
                    st.dataframe(con.execute(f"SELECT * FROM {u['table']} LIMIT 20").fetchdf(), width='stretch')

elif st.session_state["page"] == "📖 Dataset Overview":
    st.markdown('<p class="page-title">Dataset Overview</p>', unsafe_allow_html=True)
    st.markdown('<p class="page-subtitle">The business story behind the data, so you know exactly what you can ask.</p>', unsafe_allow_html=True)

    with st.container(border=True):
        st.markdown('<p class="section-title">The business behind the data</p>', unsafe_allow_html=True)
        st.markdown(
            "**Olist** is a Brazilian e-commerce marketplace that connects small and medium "
            "businesses to major online marketplaces. Every row in this dataset traces one order "
            "through its full lifecycle: a **customer** places an **order**, the order is made up of "
            "one or more **items** (products from **sellers**), the customer **pays** for it, the order "
            "gets **delivered**, and afterwards the customer leaves a **review**. This app can answer "
            "questions about any point in that journey — revenue, delivery speed, payment habits, "
            "customer location, and satisfaction."
        )

    with st.container(border=True):
        st.markdown('<p class="section-title">The 6 tables, in plain English</p>', unsafe_allow_html=True)
        table_rows = [
            ("orders", "One row per order", "Order status, and every timestamp: purchase, approval, carrier hand-off, delivery, and the original estimate."),
            ("customers", "Who placed each order", "Customer ID, and their city/state — the basis for every geography question."),
            ("order_items", "The products inside each order", "Links an order to its product(s) and seller(s), with the price and freight (shipping) cost of each item."),
            ("products", "The product catalog", "Category name, plus physical details like weight and dimensions."),
            ("payments", "How each order was paid for", "Payment type (credit card, boleto, etc.), number of installments, and the amount paid."),
            ("reviews", "Customer feedback", "The 1-5 star review score, plus any written comment left after the order."),
        ]
        rows_html = "".join(
            f"<tr><td><b>{t}</b></td><td>{desc}</td><td>{detail}</td></tr>"
            for t, desc, detail in table_rows
        )
        st.markdown(
            f'<table class="overview-table"><tr><th>Table</th><th>What it is</th><th>What\'s in it</th></tr>{rows_html}</table>',
            unsafe_allow_html=True
        )

    with st.container(border=True):
        st.markdown('<p class="section-title">What you can ask, by topic</p>', unsafe_allow_html=True)
        st.caption("Every category below has a full list of ready-made questions on the Dashboard and Chat Analyst pages.")
        for category, questions in QUESTION_BANK.items():
            with st.expander(f"{category}  ({len(questions)} questions)"):
                for q in questions:
                    st.markdown(f"- {q}")

    with st.container(border=True):
        st.markdown('<p class="section-title">Have your own data?</p>', unsafe_allow_html=True)
        st.markdown(
            "This isn't limited to the Olist dataset. Head to **📁 My Data** to upload your own "
            "CSV or Excel file — it becomes a new table the AI can query immediately, using the "
            "exact same chat interface described above."
        )
