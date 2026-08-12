import streamlit as st
from ask import ask_question, validate_result, auto_chart, generate_insight, con

# =========================================================
# PAGE CONFIG
# =========================================================
st.set_page_config(
    page_title="AI Data Analyst Agent",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

# =========================================================
# KPI DATA — cached so the database isn't hit on every rerun
# =========================================================
@st.cache_data
def load_kpis():
    # COALESCE(..., 0) protects against a NULL result if a table were ever
    # empty or a column had only missing values — the KPI shows 0 instead
    # of crashing or displaying "None".
    total_orders = con.execute("SELECT COALESCE(COUNT(*), 0) FROM orders").fetchone()[0]
    total_revenue = con.execute("SELECT COALESCE(SUM(payment_value), 0) FROM payments").fetchone()[0]
    avg_review = con.execute("SELECT COALESCE(AVG(review_score), 0) FROM reviews").fetchone()[0]
    total_customers = con.execute("SELECT COALESCE(COUNT(DISTINCT customer_id), 0) FROM customers").fetchone()[0]
    return total_orders, total_revenue, avg_review, total_customers

total_orders, total_revenue, avg_review, total_customers = load_kpis()

# Table count is read from the database itself, not hardcoded — so the
# sidebar always reflects whatever tables actually got loaded.
num_tables = con.execute("SHOW TABLES").fetchdf().shape[0]

# =========================================================
# SESSION STATE — holds whatever question is currently in the box
# =========================================================
if "question" not in st.session_state:
    st.session_state["question"] = ""

def set_question(q):
    """Called when an example button is clicked — fills the input box."""
    st.session_state["question"] = q

# =========================================================
# CUSTOM CSS — warm cream AI-dashboard theme
# =========================================================
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;500;600;700&family=Inter:wght@400;500;600;700;800&display=swap');

    html, body, [class*="css"] { font-family: 'Inter', sans-serif; }

    /* ---- Warm cream background ---- */
    .stApp {
        background: linear-gradient(160deg, #faf6ee 0%, #f3ecdc 100%);
    }

    #MainMenu, footer, header {visibility: hidden;}

    /* ---- Sidebar ---- */
    section[data-testid="stSidebar"] {
        background-color: #fffdf8;
        border-right: 1px solid #ece3d0;
    }
    .sidebar-brand {
        font-family: 'Space Grotesk', sans-serif;
        font-size: 1.25rem;
        font-weight: 700;
        color: #3d3425;
        padding: 0.5rem 0 0.2rem 0;
    }
    .ai-badge {
        display: inline-flex;
        align-items: center;
        gap: 0.4rem;
        background: #eafbe7;
        color: #16a34a;
        font-size: 0.78rem;
        font-weight: 600;
        padding: 0.3rem 0.7rem;
        border-radius: 999px;
        margin-bottom: 1.4rem;
    }
    .pulse-dot {
        width: 7px; height: 7px;
        background: #22c55e;
        border-radius: 50%;
        animation: pulse 1.6s infinite;
    }
    @keyframes pulse {
        0% { box-shadow: 0 0 0 0 rgba(34,197,94,0.5); }
        70% { box-shadow: 0 0 0 6px rgba(34,197,94,0); }
        100% { box-shadow: 0 0 0 0 rgba(34,197,94,0); }
    }
    .sidebar-item {
        color: #8a7f68;
        font-size: 0.9rem;
        padding: 0.5rem 0.75rem;
        border-radius: 10px;
        margin-bottom: 0.25rem;
    }
    .sidebar-item-active {
        background-color: #fdf1dd;
        color: #b8720a;
        font-weight: 600;
        font-size: 0.9rem;
        padding: 0.5rem 0.75rem;
        border-radius: 10px;
        margin-bottom: 0.25rem;
    }

    /* ---- Page title ---- */
    .page-title {
        font-family: 'Space Grotesk', sans-serif;
        font-size: 1.9rem;
        font-weight: 700;
        color: #3d3425;
        margin-bottom: 0.1rem;
    }
    .page-subtitle {
        color: #a39a85;
        font-size: 0.95rem;
        margin-bottom: 1.6rem;
    }

    /* ---- KPI cards ---- */
    .kpi-card {
        background: linear-gradient(145deg, #fffdf9, #fbf4e6);
        border-radius: 16px;
        padding: 1.3rem 1.4rem;
        box-shadow: 0 6px 20px rgba(180,140,60,0.08);
        border: 1px solid #f1e6cd;
    }
    .kpi-label {
        color: #a89c7f;
        font-size: 0.8rem;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.04em;
    }
    .kpi-value {
        color: #3d3425;
        font-size: 1.65rem;
        font-weight: 800;
        margin-top: 0.2rem;
    }
    .kpi-icon {
        font-size: 1.3rem;
        background: #fdf1dd;
        padding: 0.5rem 0.65rem;
        border-radius: 10px;
        display: inline-block;
        margin-bottom: 0.6rem;
    }

    /* ---- Section cards ---- */
    .section-card {
        background-color: #fffdf9;
        border-radius: 16px;
        padding: 1.5rem 1.6rem;
        margin-bottom: 1.2rem;
        box-shadow: 0 6px 20px rgba(180,140,60,0.08);
        border: 1px solid #f1e6cd;
    }
    .section-title {
        color: #b8720a;
        font-size: 0.78rem;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 0.06em;
        margin-bottom: 0.8rem;
    }

    /* ---- Input ---- */
    .stTextInput>div>div>input {
        background-color: #fffaf0;
        color: #3d3425;
        border: 1px solid #ecdfc2;
        border-radius: 12px;
        padding: 0.85rem 1.1rem;
        font-size: 1rem;
    }
    .stTextInput>div>div>input:focus {
        border: 1px solid #d97706;
        box-shadow: 0 0 0 3px rgba(217,119,6,0.12);
    }

    /* ---- Primary Analyze button ---- */
    .stButton>button {
        border-radius: 12px;
        font-weight: 700;
        transition: all 0.2s ease;
    }
    div[data-testid="stButton"] button[kind="primary"] {
        background: linear-gradient(90deg, #d97706, #ea580c);
        color: white;
        border: none;
        padding: 0.7rem 2.2rem;
        box-shadow: 0 4px 14px rgba(217,119,6,0.3);
    }
    div[data-testid="stButton"] button[kind="primary"]:hover {
        transform: translateY(-2px);
        box-shadow: 0 6px 18px rgba(217,119,6,0.4);
    }

    /* ---- Example question chip-buttons (secondary buttons) ---- */
    div[data-testid="stButton"] button[kind="secondary"] {
        background-color: #fffaf0;
        color: #8a5a1c;
        border: 1px solid #ecdfc2;
        border-radius: 999px;
        padding: 0.4rem 1rem;
        font-size: 0.83rem;
        font-weight: 500;
        box-shadow: none;
    }
    div[data-testid="stButton"] button[kind="secondary"]:hover {
        background-color: #fdf1dd;
        border-color: #d97706;
        color: #b8720a;
        transform: none;
    }

    /* ---- Insight box ---- */
    .insight-box {
        background: linear-gradient(135deg, #fef6e8, #fdeee0);
        border: 1px solid #f6dfb8;
        border-left: 4px solid #d97706;
        padding: 1.2rem 1.5rem;
        border-radius: 12px;
        color: #4a4230;
        line-height: 1.65;
    }

    .status-ok { color: #16a34a; font-weight: 600; font-size: 0.9rem; }
    .status-warn { color: #d97706; font-weight: 600; font-size: 0.9rem; }
</style>
""", unsafe_allow_html=True)

# =========================================================
# SIDEBAR
# =========================================================
with st.sidebar:
    st.markdown('<p class="sidebar-brand">📊 AI Data Analyst</p>', unsafe_allow_html=True)
    st.markdown('<div class="ai-badge"><span class="pulse-dot"></span> Gemini AI Ready</div>', unsafe_allow_html=True)
    st.markdown('<p class="sidebar-item-active">🏠 Dashboard</p>', unsafe_allow_html=True)
    st.markdown('<p class="sidebar-item">🗂️ Dataset: Olist E-commerce</p>', unsafe_allow_html=True)
    st.markdown('<p class="sidebar-item">🧠 Model: Gemini 3.6 Flash</p>', unsafe_allow_html=True)
    st.markdown(f'<p class="sidebar-item">🗄️ {num_tables} tables auto-detected</p>', unsafe_allow_html=True)

# =========================================================
# PAGE HEADER
# =========================================================
st.markdown('<p class="page-title">Dashboard</p>', unsafe_allow_html=True)
st.markdown('<p class="page-subtitle">Ask any business question about the Olist e-commerce dataset — powered by Gemini.</p>', unsafe_allow_html=True)

# =========================================================
# KPI ROW
# =========================================================
k1, k2, k3, k4 = st.columns(4)

with k1:
    st.markdown(f"""
    <div class="kpi-card">
        <div class="kpi-icon">📦</div>
        <div class="kpi-label">Total Orders</div>
        <div class="kpi-value">{total_orders:,}</div>
    </div>
    """, unsafe_allow_html=True)

with k2:
    st.markdown(f"""
    <div class="kpi-card">
        <div class="kpi-icon">💰</div>
        <div class="kpi-label">Total Revenue</div>
        <div class="kpi-value">R$ {total_revenue/1_000_000:.1f}M</div>
    </div>
    """, unsafe_allow_html=True)

with k3:
    st.markdown(f"""
    <div class="kpi-card">
        <div class="kpi-icon">⭐</div>
        <div class="kpi-label">Avg Review Score</div>
        <div class="kpi-value">{avg_review:.2f} / 5</div>
    </div>
    """, unsafe_allow_html=True)

with k4:
    st.markdown(f"""
    <div class="kpi-card">
        <div class="kpi-icon">👥</div>
        <div class="kpi-label">Total Customers</div>
        <div class="kpi-value">{total_customers:,}</div>
    </div>
    """, unsafe_allow_html=True)

st.write("")

# =========================================================
# ASK-A-QUESTION SECTION
# =========================================================
st.markdown('<div class="section-card">', unsafe_allow_html=True)
st.markdown('<p class="section-title">Ask a question</p>', unsafe_allow_html=True)

question = st.text_input(
    "Ask a question about the data:",
    key="question",
    placeholder="e.g. Which product category had the highest total revenue?",
    label_visibility="collapsed"
)

analyze_clicked = st.button("✨ Analyze", type="primary")

st.write("")
st.markdown('<p style="color:#a89c7f; font-size:0.82rem; font-weight:600; margin-bottom:0.5rem;">OR PICK FROM THE LIST</p>', unsafe_allow_html=True)

# ---- One dropdown with every example question ----
ALL_QUESTIONS = [
    "Which product category had the highest total revenue?",
    "What are the top 5 product categories by total revenue?",
    "What is the total revenue from all orders?",
    "What is the average order value?",
    "Which product category has the most orders?",
    "What is the average price per product category?",
    "How many orders were delivered late?",
    "What is the average delivery time in days?",
    "Which state has the most delayed deliveries?",
    "Which state has the most customers?",
    "How many unique customers are there?",
    "Which city has the highest number of orders?",
    "What is the most common payment type?",
    "What is the average payment value?",
    "How many orders used more than one payment installment?",
    "What is the average review score?",
    "How many orders have a review score of 5?",
    "How many orders have a review score of 1 or 2?",
    "How many orders are there in total?",
    "What percentage of orders were cancelled?",
]

def set_question_from_dropdown():
    picked = st.session_state["dropdown_pick"]
    if picked != "-- Select a question --":
        st.session_state["question"] = picked

st.selectbox(
    "Pick an example question",
    options=["-- Select a question --"] + ALL_QUESTIONS,
    key="dropdown_pick",
    on_change=set_question_from_dropdown,
    label_visibility="collapsed"
)

st.markdown('</div>', unsafe_allow_html=True)

# =========================================================
# RESULTS
# =========================================================
if analyze_clicked and question:
    with st.spinner("Thinking..."):
        try:
            sql, df = ask_question(question)
            is_valid, reason = validate_result(df)
        except Exception as e:
            st.error(f"Something went wrong: {e}")
            st.stop()

    if is_valid:
        st.markdown(f'<p class="status-ok">✓ {reason}</p>', unsafe_allow_html=True)
    else:
        st.markdown(f'<p class="status-warn">⚠ {reason}</p>', unsafe_allow_html=True)

    st.markdown('<div class="section-card">', unsafe_allow_html=True)
    st.markdown('<p class="section-title">Generated SQL</p>', unsafe_allow_html=True)
    st.code(sql, language="sql")
    st.markdown('</div>', unsafe_allow_html=True)

    col1, col2 = st.columns(2)

    with col1:
        st.markdown('<div class="section-card">', unsafe_allow_html=True)
        st.markdown('<p class="section-title">Result</p>', unsafe_allow_html=True)
        st.dataframe(df, use_container_width=True)
        st.markdown('</div>', unsafe_allow_html=True)

    with col2:
        st.markdown('<div class="section-card">', unsafe_allow_html=True)
        st.markdown('<p class="section-title">Chart</p>', unsafe_allow_html=True)
        fig = auto_chart(df)
        if fig:
            fig.update_layout(
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
                font_color="#4a4230",
                margin=dict(l=10, r=10, t=10, b=10)
            )
            fig.update_traces(marker_color="#d97706")
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No chart available for this result shape.")
        st.markdown('</div>', unsafe_allow_html=True)

    with st.spinner("Writing insight..."):
        insight = generate_insight(question, df)

    st.markdown('<p class="section-title">Insight</p>', unsafe_allow_html=True)
    st.markdown(f'<div class="insight-box">🤖 {insight}</div>', unsafe_allow_html=True)

elif analyze_clicked and not question:
    st.warning("Please type a question first.")
