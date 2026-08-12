import streamlit as st
from ask import (
    ask_question, validate_result, auto_chart, generate_insight, con,
    detect_anomalies, load_uploaded_file, list_tables, DEFAULT_TABLES
)

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


def process_question(question):
    history = [{"question": t["question"], "sql": t["sql"]} for t in st.session_state["chat_history"]]
    try:
        sql, df = ask_question(question, history=history, table_filter=st.session_state["active_tables"])
        is_valid, reason = validate_result(df)
        insight = generate_insight(question, df, history=history)
        fig = auto_chart(df)
        st.session_state["chat_history"].append({
            "question": question, "sql": sql, "df": df,
            "valid": is_valid, "reason": reason, "insight": insight, "fig": fig, "error": None
        })
    except Exception as e:
        st.session_state["chat_history"].append({
            "question": question, "sql": None, "df": None,
            "valid": False, "reason": None, "insight": None, "fig": None, "error": str(e)
        })


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
    @import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@500;600;700;800&family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap');

    html, body, [class*="css"] { font-family: 'Inter', sans-serif; }

    /* ---- Warm creamy background with soft glow ---- */
    .stApp {
        background:
            radial-gradient(circle at 12% 0%, rgba(217,119,6,0.08) 0%, transparent 42%),
            radial-gradient(circle at 88% 12%, rgba(180,83,9,0.07) 0%, transparent 45%),
            linear-gradient(160deg, #fbf7ee 0%, #f4ecdb 100%);
        background-attachment: fixed;
    }
    #MainMenu, footer, header {visibility: hidden;}

    ::-webkit-scrollbar { width: 8px; height: 8px; }
    ::-webkit-scrollbar-thumb { background: #e6d8b8; border-radius: 8px; }

    /* ---- Sidebar ---- */
    section[data-testid="stSidebar"] {
        background: linear-gradient(180deg, #fffdf8 0%, #fdf8ec 100%);
        border-right: 1px solid #ece0c4;
    }
    .brand-row { display:flex; align-items:center; gap:0.55rem; padding: 0.4rem 0 0.1rem 0; }
    .brand-mark {
        width: 34px; height: 34px; border-radius: 10px;
        background: linear-gradient(135deg, #d97706, #f59e0b);
        display:flex; align-items:center; justify-content:center;
        font-size: 1.05rem; box-shadow: 0 0 16px rgba(217,119,6,0.30);
    }
    .sidebar-brand {
        font-family: 'Space Grotesk', sans-serif;
        font-size: 1.15rem; font-weight: 700; color: #3d3425;
    }
    .sidebar-sub { color:#a89c7f; font-size:0.72rem; letter-spacing:0.04em; margin: 0 0 1.1rem 2.6rem; }
    .ai-badge {
        display: inline-flex; align-items: center; gap: 0.45rem;
        background: rgba(22,163,74,0.10); color: #15803d;
        font-size: 0.78rem; font-weight: 600;
        padding: 0.35rem 0.75rem; border-radius: 999px;
        margin-bottom: 1.3rem; border: 1px solid rgba(22,163,74,0.22);
    }
    .pulse-dot {
        width: 7px; height: 7px; background: #22c55e; border-radius: 50%;
        animation: pulse 1.6s infinite;
    }
    @keyframes pulse {
        0% { box-shadow: 0 0 0 0 rgba(34,197,94,0.5); }
        70% { box-shadow: 0 0 0 7px rgba(34,197,94,0); }
        100% { box-shadow: 0 0 0 0 rgba(34,197,94,0); }
    }
    .scope-pill {
        display:inline-block; background: rgba(217,119,6,0.09); color:#b8720a;
        border: 1px solid rgba(217,119,6,0.22); border-radius: 999px;
        padding: 0.2rem 0.6rem; font-size: 0.72rem; font-weight: 600;
        margin: 0.15rem 0.25rem 0.15rem 0;
    }

    /* ---- Nav radio styled as sidebar list ---- */
    section[data-testid="stSidebar"] div[role="radiogroup"] label {
        background: transparent; color: #8a7f68; border-radius: 10px;
        padding: 0.55rem 0.75rem; margin-bottom: 0.2rem; font-weight: 500; width: 100%;
        transition: all 0.15s ease;
    }
    section[data-testid="stSidebar"] div[role="radiogroup"] label:hover { background: #fdf1dd; color:#3d3425; }

    /* ---- Page title ---- */
    .page-title {
        font-family: 'Space Grotesk', sans-serif;
        font-size: 2rem; font-weight: 700;
        background: linear-gradient(90deg, #3d3425 20%, #b8720a 65%, #d97706 100%);
        -webkit-background-clip: text; background-clip: text; color: transparent;
        margin-bottom: 0.15rem;
    }
    .page-subtitle { color: #a39a85; font-size: 0.95rem; margin-bottom: 1.6rem; }

    /* ---- Glass cards ---- */
    .kpi-card, .section-card, .glass-card {
        background: rgba(255, 253, 248, 0.75);
        backdrop-filter: blur(14px);
        border-radius: 16px;
        border: 1px solid rgba(217,119,6,0.12);
        box-shadow: 0 8px 26px rgba(180,140,60,0.10);
    }
    .kpi-card { padding: 1.3rem 1.4rem; transition: transform 0.15s ease, border-color 0.15s ease; }
    .kpi-card:hover { transform: translateY(-3px); border-color: rgba(217,119,6,0.35); }
    .kpi-label { color: #a89c7f; font-size: 0.78rem; font-weight: 600; text-transform: uppercase; letter-spacing: 0.06em; }
    .kpi-value { color: #3d3425; font-size: 1.65rem; font-weight: 800; margin-top: 0.2rem; font-family:'Space Grotesk',sans-serif; }
    .kpi-icon {
        font-size: 1.2rem; background: rgba(217,119,6,0.10); border: 1px solid rgba(217,119,6,0.2);
        padding: 0.5rem 0.65rem; border-radius: 10px; display: inline-block; margin-bottom: 0.6rem;
    }

    .section-card { padding: 1.5rem 1.6rem; margin-bottom: 1.2rem; }
    .section-title {
        color: #b8720a; font-size: 0.76rem; font-weight: 700;
        text-transform: uppercase; letter-spacing: 0.08em; margin-bottom: 0.8rem;
    }

    /* ---- Inputs ---- */
    .stTextInput>div>div>input, .stChatInput textarea, .stSelectbox>div>div {
        background-color: #fffaf0 !important; color: #3d3425 !important;
        border: 1px solid #ecdfc2 !important; border-radius: 12px !important;
    }
    .stTextInput>div>div>input:focus { border: 1px solid #d97706 !important; box-shadow: 0 0 0 3px rgba(217,119,6,0.12) !important; }

    /* ---- Buttons ---- */
    .stButton>button { border-radius: 12px; font-weight: 700; transition: all 0.2s ease; }
    div[data-testid="stButton"] button[kind="primary"] {
        background: linear-gradient(90deg, #d97706, #ea580c); color: white; border: none;
        padding: 0.7rem 2.2rem; box-shadow: 0 4px 16px rgba(217,119,6,0.30);
    }
    div[data-testid="stButton"] button[kind="primary"]:hover { transform: translateY(-2px); box-shadow: 0 6px 20px rgba(217,119,6,0.42); }
    div[data-testid="stButton"] button[kind="secondary"] {
        background-color: #fffaf0; color: #8a5a1c; border: 1px solid #ecdfc2;
        border-radius: 999px; padding: 0.4rem 1rem; font-size: 0.83rem; font-weight: 500; box-shadow:none;
    }
    div[data-testid="stButton"] button[kind="secondary"]:hover { background-color: #fdf1dd; border-color: #d97706; color: #b8720a; }

    /* ---- Insight / anomaly boxes ---- */
    .insight-box {
        background: linear-gradient(135deg, rgba(217,119,6,0.08), rgba(234,88,12,0.06));
        border: 1px solid rgba(217,119,6,0.2); border-left: 4px solid #d97706;
        padding: 1.1rem 1.4rem; border-radius: 12px; color: #4a4230; line-height: 1.65;
    }
    .anomaly-box {
        background: linear-gradient(135deg, rgba(220,38,38,0.07), rgba(217,119,6,0.06));
        border: 1px solid rgba(220,38,38,0.20); border-left: 4px solid #dc2626;
        padding: 1.1rem 1.4rem; border-radius: 12px; color: #4a4230; line-height: 1.65;
    }
    .stat-chip {
        display:inline-block; background:#fffaf0; border:1px solid #ecdfc2; border-radius: 10px;
        padding: 0.5rem 0.8rem; margin: 0.2rem 0.3rem 0.2rem 0; font-size: 0.8rem; color:#8a7f68;
    }
    .stat-chip b { color:#3d3425; }

    .status-ok { color: #16a34a; font-weight: 600; font-size: 0.9rem; }
    .status-warn { color: #d97706; font-weight: 600; font-size: 0.9rem; }
    .status-err { color: #dc2626; font-weight: 600; font-size: 0.9rem; }

    /* ---- Chat bubbles ---- */
    div[data-testid="stChatMessage"] {
        background: rgba(255,253,248,0.7); border: 1px solid rgba(217,119,6,0.12);
        border-radius: 14px; backdrop-filter: blur(10px);
    }
    code, .stCode { font-family: 'JetBrains Mono', monospace !important; }

    /* ---- Overview page tables ---- */
    .overview-table { width:100%; border-collapse: collapse; font-size: 0.88rem; }
    .overview-table th { text-align:left; color:#b8720a; font-size:0.75rem; text-transform:uppercase;
        letter-spacing:0.05em; padding: 0.4rem 0.6rem; border-bottom: 2px solid #ecdfc2; }
    .overview-table td { padding: 0.45rem 0.6rem; border-bottom: 1px solid #f1e6cd; color:#4a4230; vertical-align: top; }
</style>
""", unsafe_allow_html=True)

with st.sidebar:
    st.markdown('<div class="brand-row"><div class="brand-mark">📊</div><span class="sidebar-brand">AI Data Analyst</span></div>', unsafe_allow_html=True)
    st.markdown('<p class="sidebar-sub">TEXT-TO-SQL · GEMINI-POWERED</p>', unsafe_allow_html=True)
    st.markdown('<div class="ai-badge"><span class="pulse-dot"></span> Gemini AI Ready</div>', unsafe_allow_html=True)

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

    st.write("")
    st.markdown('<div class="section-card">', unsafe_allow_html=True)
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
    st.markdown('</div>', unsafe_allow_html=True)

    st.markdown('<div class="section-card">', unsafe_allow_html=True)
    st.markdown('<p class="section-title">Or browse every question you can ask</p>', unsafe_allow_html=True)
    st.caption("Not sure what to ask? Every question the AI can reliably answer about this dataset is listed here, grouped by topic.")
    st.selectbox(
        "Pick any question",
        options=build_dropdown_options(),
        key="dropdown_pick",
        on_change=pick_from_dropdown,
        label_visibility="collapsed",
    )
    st.markdown('</div>', unsafe_allow_html=True)

    if st.session_state["chat_history"]:
        st.markdown('<div class="section-card">', unsafe_allow_html=True)
        st.markdown('<p class="section-title">Recent conversation</p>', unsafe_allow_html=True)
        for turn in st.session_state["chat_history"][-3:]:
            st.markdown(f"**Q:** {turn['question']}")
            if turn.get("insight"):
                st.markdown(f'<div class="insight-box" style="margin-bottom:0.8rem;">🤖 {turn["insight"]}</div>', unsafe_allow_html=True)
        st.markdown('</div>', unsafe_allow_html=True)

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

    for turn in st.session_state["chat_history"]:
        with st.chat_message("user"):
            st.markdown(turn["question"])
        with st.chat_message("assistant", avatar="📊"):
            if turn["error"]:
                st.markdown(f'<p class="status-err">✗ {turn["error"]}</p>', unsafe_allow_html=True)
                continue

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
                        font_color="#4a4230", margin=dict(l=10, r=10, t=10, b=10),
                        height=260,
                    )
                    st.plotly_chart(fig, width='stretch')
                else:
                    st.info("No chart available for this result shape.")

            st.markdown(f'<div class="insight-box">🤖 {turn["insight"]}</div>', unsafe_allow_html=True)

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
        '<p style="color:#4a4230; line-height:1.6;">In simple words: click the button below and the AI '
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

        st.markdown('<div class="anomaly-box">🚨 ' + narrative.replace("\n", "<br>") + '</div>', unsafe_allow_html=True)
        st.write("")

        if findings:
            st.markdown('<div class="section-card">', unsafe_allow_html=True)
            st.markdown('<p class="section-title">Raw statistical findings</p>', unsafe_allow_html=True)
            for f in findings:
                st.markdown(
                    f'<span class="stat-chip"><b>{f["table"]}.{f["column"]}</b> — '
                    f'{f["outlier_count"]} outliers ({f["pct_of_sample"]}%), '
                    f'mean <b>{f["mean"]:.1f}</b>, extreme value <b>{f["max_outlier"]:.1f}</b></span>',
                    unsafe_allow_html=True
                )
            st.markdown('</div>', unsafe_allow_html=True)
    else:
        st.info("Click **Scan for anomalies** to run the check.")

elif st.session_state["page"] == "📁 My Data":
    st.markdown('<p class="page-title">My Data</p>', unsafe_allow_html=True)
    st.markdown('<p class="page-subtitle">Upload your own CSV or Excel file and the AI can start answering questions about it immediately.</p>', unsafe_allow_html=True)

    st.markdown('<div class="section-card">', unsafe_allow_html=True)
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
    st.markdown('</div>', unsafe_allow_html=True)

    st.markdown('<div class="section-card">', unsafe_allow_html=True)
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
    st.markdown('</div>', unsafe_allow_html=True)

    if st.session_state["uploaded_tables"]:
        st.markdown('<div class="section-card">', unsafe_allow_html=True)
        st.markdown('<p class="section-title">Your uploaded tables</p>', unsafe_allow_html=True)
        for u in st.session_state["uploaded_tables"]:
            st.markdown(f'<span class="stat-chip"><b>{u["table"]}</b> — from {u["filename"]}, {u["rows"]:,} rows</span>', unsafe_allow_html=True)
            with st.expander(f"Preview {u['table']}"):
                st.dataframe(con.execute(f"SELECT * FROM {u['table']} LIMIT 20").fetchdf(), width='stretch')
        st.markdown('</div>', unsafe_allow_html=True)

elif st.session_state["page"] == "📖 Dataset Overview":
    st.markdown('<p class="page-title">Dataset Overview</p>', unsafe_allow_html=True)
    st.markdown('<p class="page-subtitle">The business story behind the data, so you know exactly what you can ask.</p>', unsafe_allow_html=True)

    st.markdown('<div class="section-card">', unsafe_allow_html=True)
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
    st.markdown('</div>', unsafe_allow_html=True)

    st.markdown('<div class="section-card">', unsafe_allow_html=True)
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
    st.markdown('</div>', unsafe_allow_html=True)

    st.markdown('<div class="section-card">', unsafe_allow_html=True)
    st.markdown('<p class="section-title">What you can ask, by topic</p>', unsafe_allow_html=True)
    st.caption("Every category below has a full list of ready-made questions on the Dashboard and Chat Analyst pages.")
    for category, questions in QUESTION_BANK.items():
        with st.expander(f"{category}  ({len(questions)} questions)"):
            for q in questions:
                st.markdown(f"- {q}")
    st.markdown('</div>', unsafe_allow_html=True)

    st.markdown('<div class="section-card">', unsafe_allow_html=True)
    st.markdown('<p class="section-title">Have your own data?</p>', unsafe_allow_html=True)
    st.markdown(
        "This isn't limited to the Olist dataset. Head to **📁 My Data** to upload your own "
        "CSV or Excel file — it becomes a new table the AI can query immediately, using the "
        "exact same chat interface described above."
    )
    st.markdown('</div>', unsafe_allow_html=True)
