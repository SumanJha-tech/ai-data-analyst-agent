# AI Data Analyst Agent — What We Did, How, and What Happened

**Date:** 2026-08-12

## What this project is

A Streamlit web app where you type a business question in plain English ("Which product
category had the highest revenue?") and it:

1. Sends your question + the database's table/column list to Google's **Gemini** AI
2. Gemini writes a **SQL** query to answer it
3. The SQL runs against a local **DuckDB** database built from the Olist e-commerce CSVs
4. The result is shown as a table, an auto-picked chart, and a short AI-written insight

## What we did today

The app worked, but was a single-shot Q&A form with no memory, locked to one dataset, and
looked like a generic light-themed dashboard. We rebuilt it to be more capable and more
distinctive:

### New features (`ask.py`)
- **Chat memory** — `format_history_for_prompt()` + a `history` parameter threaded through
  `ask_question()` and `generate_insight()`. The last 4 turns (question + SQL used) are fed
  back into every new prompt, so follow-ups like *"now break that down by state"* resolve
  correctly instead of the AI starting from zero each time.
- **Bring-your-own-dataset** — `load_uploaded_file()` reads an uploaded CSV/Excel file with
  pandas and loads it into DuckDB as a new table, sanitizing the filename and column names into
  safe SQL identifiers. `get_schema_from_db()` now accepts a `table_filter` so the AI can be
  scoped to only the tables the user wants it to see (e.g. only their upload, not Olist).
- **Anomaly Radar** — `detect_anomalies()` scans every numeric column in the active tables
  (via a 20k-row sample for speed), flags statistical outliers with a z-score test, ranks the
  findings, and asks Gemini to turn the raw numbers into a plain-English "things a manager
  should worry about" summary — proactively, without the user having to ask a question first.
- **Smarter auto-charting** — `auto_chart()` now picks a line chart for time-series-shaped
  results, a pie chart for small category breakdowns, and a bar chart otherwise, instead of
  always defaulting to a bar chart.

### UI redesign (`app.py`)
- Rebuilt from a single-page light "warm cream" form into a **dark "AI command-center" theme**:
  deep charcoal/navy gradient background, glowing glass cards (`backdrop-filter: blur`), a
  gradient page title, neon cyan/amber accents, and a pulsing "AI Ready" status badge.
- Restructured into **4 pages** navigated from the sidebar:
  - **🏠 Dashboard** — KPI cards + clickable example questions
  - **💬 Chat Analyst** — the new conversational interface (`st.chat_message` bubbles), with a
    running conversation, SQL shown in an expander per turn, and a "Clear chat" button
  - **🔍 Anomaly Radar** — one-click proactive anomaly scan
  - **📁 My Data** — file upload + checkboxes to control which tables the AI is allowed to query
- Session state (`st.session_state`) now tracks the chat history, the active table scope, and
  uploaded tables, so all four pages stay in sync as you use the app.

### Dependencies
Added `openpyxl` (Excel file support) and `fpdf2` (used to generate the companion PDF
explainer) to `requirements.txt`.

## What happened when we tested it

- `ask.py` was run standalone end-to-end against the live Gemini API: schema auto-detection,
  a two-question chat-memory sequence, and the anomaly scan all completed successfully. Sample
  real output:
  - *"Which product category had the highest total revenue?"* → correctly identified
    `beleza_saude` (Health & Beauty) at **R$1,258,681.34**, with SQL and a written insight.
  - The Anomaly Radar found real, sensible issues in the Olist data on its own: freight costs
    spiking to **R$314.40** (15x the average), some orders with up to **24 payment installments**,
    and products as heavy as **30kg** — all flagged and explained in plain English.
- Fixed a pandas 4.0 deprecation warning in `clean_dataframe()` found during the test run.
- `app.py` was launched with `streamlit run` and confirmed to boot cleanly (HTTP 200, no errors
  in the server log).
- Automated in-browser visual verification (via the Chrome browser tool) could not be completed
  in this environment — the browser tab repeatedly failed to render `localhost:8501` even though
  the server itself was confirmed healthy. **Recommendation: open `http://localhost:8501`
  yourself to see the new UI**, since it wasn't possible to visually confirm it end-to-end here.

## How to run it

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy RemoteSigned
& d:\Project\AI_Data_Analyst_Agent\venv\Scripts\Activate.ps1
python load_Data.py        # only needed once, or after changing the CSVs
streamlit run app.py
```

Then open the URL Streamlit prints (usually `http://localhost:8501`).

## Files changed
- `ask.py` — rewritten (chat memory, table scoping, anomaly detection, file upload)
- `app.py` — rewritten (dark theme, 4-page navigation, chat UI)
- `requirements.txt` — added `openpyxl`, `fpdf2`
- `PROJECT_SUMMARY.md` — this file
- `AI_Data_Analyst_Agent_Explained.pdf` — full plain-English, code-by-code walkthrough of the
  entire project (see the PDF for details on every function)

## Known limitations / possible next steps
- Anomaly detection is purely statistical (z-score) — it doesn't know business context, so it
  can flag things that are unusual but expected (e.g. a legitimately large wholesale order).
- Chat memory only looks at the last 4 turns — very long conversations will "forget" early
  context.
- The dark UI was not visually verified in a live browser during this session (see testing notes
  above) — worth a quick manual look before considering this fully done.
