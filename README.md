[README.md](https://github.com/user-attachments/files/30992431/README.md)
# 📊 AI Data Analyst Agent

Ask a business question in plain English. Get back a validated SQL query, a result table, an auto-picked chart, and a written insight — in seconds, with no SQL knowledge required.

**🔗 Live app:** [ai-data-analyst-agent-ge2wddq5x2zrynlgqiffr5.streamlit.app](https://ai-data-analyst-agent-ge2wddq5x2zrynlgqiffr5.streamlit.app/)
**💻 Source code:** [github.com/SumanJha-tech/ai-data-analyst-agent](https://github.com/SumanJha-tech/ai-data-analyst-agent)

---

## What it does

Type a question like *"Which product category had the highest total revenue?"* and the app:

1. Looks up the live database schema (tables/columns), so the AI never has to guess
2. Sends your question + schema + recent conversation to **Gemini**, asking for one SQL query
3. Runs that query on **DuckDB**, self-correcting up to 2 times if the query fails
4. Cleans the result, picks a sensible chart type, and asks Gemini to explain it in plain English
5. Shows everything as one chat turn — SQL, table, chart, and insight — and remembers it for follow-ups

No installation needed to try it — the live link works in any browser.

---

## Why it exists

Most people who need answers from data — managers, founders, support leads — don't know SQL and don't have time to wait on an analyst. This project puts a data analyst's workflow behind a plain-English chat box:

- Real answers in seconds, not days
- Bring your own spreadsheet and start asking questions immediately
- Get warned about problems in the data (outliers, anomalies) without knowing what to look for
- Every answer shows its work — the exact SQL and a plain-English explanation — so it's trustworthy, not a black box

---

## What makes it different from a basic text-to-SQL demo

| Feature | What it means |
|---|---|
| 🧠 **Conversation memory** | Ask a follow-up like *"now just the top 3"* — it understands what "that" refers to |
| 📁 **Bring your own data** | Upload any CSV/Excel file on the *My Data* page — same chat interface, any dataset |
| 🚨 **Anomaly Radar** | Proactively scans the data for statistically unusual values and explains which ones actually matter |
| 📖 **Dataset Overview page** | Explains the business story behind the data and lists ~50 ready-made questions, grouped by topic |
| 🌍 **Actually live** | Deployed and reachable by anyone with the link, free, with zero setup |

---

## Tech stack

| Tool | Role |
|---|---|
| **Gemini (`gemini-3.6-flash`)** | Converts English questions to SQL, writes insights, narrates anomalies |
| **DuckDB** | Lightweight, file-based SQL database — no server needed |
| **Streamlit** | Turns the Python backend into an interactive multi-page web dashboard |
| **Plotly** | Auto-generates line / pie / bar charts based on result shape |
| **Pandas** | Cleans and reshapes query results |

---

## The 5 pages

- **Dashboard** — KPI cards (orders, revenue, review score, customers), clickable example questions, and a dropdown of every ready-made question
- **Chat Analyst** — the main conversation: each turn shows the question, a validity check, the SQL (collapsible), the result table, the chart, and the insight
- **Anomaly Radar** — one click runs a full statistical scan and explains, in plain English, which outliers matter
- **My Data** — upload your own CSV/Excel and choose which tables the AI should consider
- **Dataset Overview** — the business story behind the Olist dataset, plus all ~50 sample questions organized by topic

---

## The dataset

Ships with a real e-commerce dataset from **Olist** (a Brazilian marketplace), loaded into `olist.duckdb`:

- `orders` — status and purchase/delivery timestamps
- `customers` — city/state per order
- `order_items` — products per order, price and freight cost
- `products` — category, weight, dimensions
- `payments` — payment method and amount
- `reviews` — 1–5 star ratings and comments

---

## How a question becomes an answer

```
Your question
      ↓
Read live DB schema (never guesses table/column names)
      ↓
Add last few turns of conversation (for follow-ups)
      ↓
Gemini writes ONE SQL query
      ↓
Run it on DuckDB → error? → send error back to Gemini, retry (max 2x)
      ↓
Clean result → auto-pick chart type → Gemini writes plain-English insight
      ↓
Shown as one chat turn, remembered for next question
```

The same pipeline powers the Anomaly Radar — instead of a typed question, the app scans the data itself and asks Gemini to explain what it found.

---

## Notable engineering details

**Self-healing database on a fresh deploy.** The first Streamlit Cloud deploy crashed with `Table with name orders does not exist!` — the database file is gitignored, so a fresh clone had no data. Fixed by adding `ensure_default_tables_loaded()`, which checks for the required tables on startup and rebuilds them from the source CSVs if missing — so the app works on any fresh environment, no manual setup step required.

**API key works both locally and on the cloud.** Locally the key comes from a `.env` file; on Streamlit Cloud there is no `.env`, so a small bridge reads it from Streamlit's Secrets manager instead and copies it into the environment variable Gemini's client expects.

**Callback-safe page navigation.** Clicking an example question originally crashed with a `StreamlitAPIException` because page state was being changed directly inside a button's `if`-block, after the sidebar widget owning that key had already rendered. Fixed by moving all page-changing logic into `on_click` callbacks, which run *before* the page redraws. Verified with Streamlit's `AppTest` framework simulating real clicks across all 5 pages.

---

## Run it locally

```bash
git clone https://github.com/SumanJha-tech/ai-data-analyst-agent.git
cd ai-data-analyst-agent

python -m venv venv
venv\Scripts\activate        # Windows
# source venv/bin/activate   # Mac/Linux

pip install -r requirements.txt
python load_Data.py           # first time only — loads CSVs into DuckDB

streamlit run app.py
```

You'll need a free [Gemini API key](https://aistudio.google.com/apikey) in a local `.env` file:

```
GEMINI_API_KEY=your_key_here
```

The app opens at `http://localhost:8501`.

---

## What was tested

- **Schema detection** — correctly lists all 6 tables and exact columns straight from the live database
- **Chat memory** — a two-question sequence ("top category" → "now top 5") both resolved correctly
- **Anomaly Radar** — found real issues in the data: freight costs spiking over 15x the average, orders split across up to 24 payment installments vs. an average of 2.87
- **Navigation** — all 5 pages, the question dropdown, a live Gemini call, the clear-chat button, and a live anomaly scan all verified with zero exceptions via Streamlit's `AppTest`
- **Deployment** — root-caused and fixed the fresh-clone database issue rather than patching around it

---

## Skills demonstrated

- Writing and debugging real SQL against a multi-table relational schema
- Calling an LLM API (Gemini) — prompting, parsing responses, self-correction loops
- Designing an agent loop: generate → run → validate → retry
- Statistical anomaly detection (z-scores) on live tabular data
- Building a stateful, multi-page interactive UI in Streamlit
- Diagnosing and fixing a real production deployment failure
- Structuring and deploying a public GitHub repo with proper secret management
