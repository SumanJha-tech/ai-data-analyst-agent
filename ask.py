import re
import duckdb
import pandas as pd
from google import genai
from dotenv import load_dotenv

load_dotenv()
client = genai.Client()
con = duckdb.connect("olist.duckdb")

MODEL = "antigravity"

# Tables the app ships with by default. Uploaded files are added on top of this.
DEFAULT_TABLES = ["orders", "customers", "order_items", "products", "payments", "reviews"]


def get_schema_from_db(con, table_filter=None):
    """table_filter restricts which tables Gemini is even told about, so it
    can be scoped to only an uploaded file instead of the full database."""
    tables = con.execute("SHOW TABLES").fetchdf()
    names = tables["name"].tolist()
    if table_filter:
        names = [n for n in names if n in table_filter]

    schema_text = ""
    for table in names:
        columns = con.execute(f"DESCRIBE {table}").fetchdf()
        col_names = ", ".join(columns["column_name"])
        schema_text += f"{table}({col_names})\n"
    return schema_text


def list_tables(con):
    return con.execute("SHOW TABLES").fetchdf()["name"].tolist()


def clean_dataframe(df):
    df = df.copy()
    text_cols = df.select_dtypes(include=["object", "string"]).columns
    for col in text_cols:
        df[col] = df[col].fillna("Unknown")
    return df.dropna(how="all")


def format_history_for_prompt(history, max_turns=4):
    """Renders the last few Q&A turns as text so Gemini can resolve
    follow-ups like "now split that by state"."""
    if not history:
        return ""

    recent = history[-max_turns:]
    lines = ["Conversation so far (most recent last) — use it to resolve follow-up references like 'that', 'those', 'it', or an implied filter:"]
    for turn in recent:
        lines.append(f'- User asked: "{turn["question"]}"')
        lines.append(f"  SQL used: {turn['sql']}")
    return "\n".join(lines) + "\n"


def ask_question(question, history=None, table_filter=None, max_retries=2):
    schema = get_schema_from_db(con, table_filter)
    history_block = format_history_for_prompt(history)
    error_feedback = ""

    for attempt in range(max_retries + 1):
        prompt = f"""You are a SQL expert. Given this DuckDB schema:
{schema}
{history_block}
Write ONE SQL query (DuckDB syntax) to answer: "{question}"
Reply with ONLY the SQL query, no explanation, no markdown formatting.
{error_feedback}"""

        response = client.models.generate_content(model=MODEL, contents=prompt)
        sql = response.text.strip().strip("`").replace("sql\n", "")

        try:
            result = con.execute(sql).fetchdf()
            return sql, clean_dataframe(result)
        except Exception as e:
            print(f"Attempt {attempt + 1} failed: {e}")
            error_feedback = f"\nYour previous query failed with this error: {e}\nPlease fix it."

    raise Exception("Could not generate a working SQL query after retries.")


def validate_result(df):
    if df.empty:
        return False, "Result is empty — no rows returned."

    numeric_cols = df.select_dtypes(include="number").columns
    for col in numeric_cols:
        if df[col].isna().all():
            return False, f"Column '{col}' has no usable values (all missing)."
        if (df[col] < 0).any():
            return False, f"Column '{col}' has negative values, which looks wrong for this kind of data."

    return True, "Looks fine."


def auto_chart(df):
    import plotly.express as px

    if df.shape[1] != 2 or df.shape[0] > 20:
        return None

    label_col, value_col = df.columns[0], df.columns[1]
    if not pd.api.types.is_numeric_dtype(df[value_col]):
        return None

    if pd.api.types.is_datetime64_any_dtype(df[label_col]) or "date" in label_col.lower():
        return px.line(df, x=label_col, y=value_col, markers=True)
    if df.shape[0] <= 8:
        return px.pie(df, names=label_col, values=value_col, hole=0.45)
    return px.bar(df, x=label_col, y=value_col)


def generate_insight(question, df, history=None):
    history_block = format_history_for_prompt(history)
    prompt = f"""{history_block}
The user just asked: "{question}"
Here is the result data:
{df.to_string(index=False)}

Write a short 2-3 sentence business insight explaining what this shows. Be specific with numbers."""

    response = client.models.generate_content(model=MODEL, contents=prompt)
    return response.text.strip()


def _zscore_outliers(series, threshold=2.5):
    if series.std(ddof=0) == 0 or series.isna().all():
        return series.iloc[0:0]
    z = (series - series.mean()) / series.std(ddof=0)
    return series[z.abs() > threshold]


def detect_anomalies(con, table_filter=None):
    tables = table_filter or list_tables(con)
    findings = []

    for table in tables:
        try:
            cols = con.execute(f"DESCRIBE {table}").fetchdf()
        except Exception:
            continue

        numeric_cols = cols[cols["column_type"].str.contains(
            "INT|DOUBLE|DECIMAL|FLOAT|BIGINT", case=False, regex=True
        )]["column_name"].tolist()

        if not numeric_cols:
            continue

        row_count = con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        if row_count == 0:
            continue

        # Sample instead of scanning the full table, so this stays fast on large data.
        sample = con.execute(f"SELECT * FROM {table} USING SAMPLE 20000").fetchdf()

        for col in numeric_cols:
            if col not in sample.columns:
                continue
            series = pd.to_numeric(sample[col], errors="coerce").dropna()
            if len(series) < 10:
                continue

            outliers = _zscore_outliers(series)
            if len(outliers) == 0:
                continue

            findings.append({
                "table": table,
                "column": col,
                "outlier_count": int(len(outliers)),
                "sample_size": int(len(series)),
                "mean": float(series.mean()),
                "std": float(series.std(ddof=0)),
                "max_outlier": float(outliers.abs().max()),
                "pct_of_sample": round(100 * len(outliers) / len(series), 2),
            })

    findings.sort(key=lambda f: f["pct_of_sample"], reverse=True)
    top_findings = findings[:8]

    if not top_findings:
        return [], "No significant anomalies detected in the current dataset — the numeric columns all look statistically normal."

    findings_text = "\n".join(
        f"- Table '{f['table']}', column '{f['column']}': {f['outlier_count']} outlier value(s) "
        f"out of a {f['sample_size']}-row sample ({f['pct_of_sample']}%), average is {f['mean']:.2f} "
        f"with the most extreme outlier around {f['max_outlier']:.2f}."
        for f in top_findings
    )

    prompt = f"""You are a data analyst reviewing an automatic statistical anomaly scan.
Here are the raw statistical findings:
{findings_text}

Write a short plain-English summary (4-6 bullet points max) of the most business-relevant
anomalies here — things a manager should actually worry about (e.g. unusually high/low prices,
suspicious payment amounts, extreme delivery delays). Skip anything that looks like normal,
harmless spread in the data. Be concise and use numbers."""

    response = client.models.generate_content(model=MODEL, contents=prompt)
    return top_findings, response.text.strip()


def _sanitize_table_name(filename):
    name = re.sub(r"\.[^.]+$", "", filename)
    name = re.sub(r"[^a-zA-Z0-9_]", "_", name).lower()
    name = re.sub(r"_+", "_", name).strip("_")
    if not name or not name[0].isalpha():
        name = f"t_{name}"
    return name


def load_uploaded_file(uploaded_file, con):
    filename = uploaded_file.name
    if filename.lower().endswith((".xlsx", ".xls")):
        df = pd.read_excel(uploaded_file)
    else:
        df = pd.read_csv(uploaded_file)

    df.columns = [re.sub(r"[^a-zA-Z0-9_]", "_", str(c)).strip("_").lower() or f"col_{i}"
                  for i, c in enumerate(df.columns)]

    table_name = _sanitize_table_name(filename)
    base_name = table_name
    existing = set(list_tables(con))
    suffix = 1
    while table_name in existing:
        table_name = f"{base_name}_{suffix}"
        suffix += 1

    con.register("uploaded_df_tmp", df)
    con.execute(f"CREATE OR REPLACE TABLE {table_name} AS SELECT * FROM uploaded_df_tmp")
    con.unregister("uploaded_df_tmp")

    return table_name, len(df), list(df.columns)


if __name__ == "__main__":
    print("--- Auto-detected schema ---")
    print(get_schema_from_db(con))

    questions = [
        "Which product category had the highest total revenue? Show the category and its revenue.",
        "What are the top 5 product categories by total revenue?",
    ]

    history = []
    for question in questions:
        print("\n=================================================")
        print("Question:", question)

        sql, df = ask_question(question, history=history)
        history.append({"question": question, "sql": sql})

        print("\n--- SQL ---")
        print(sql)

        print("\n--- Result ---")
        print(df)

        is_valid, reason = validate_result(df)
        print("\n--- Validation ---")
        print(is_valid, "-", reason)

        insight = generate_insight(question, df, history=history)
        print("\n--- Insight ---")
        print(insight)

    print("\n=================================================")
    print("Anomaly scan:")
    findings, narrative = detect_anomalies(con, DEFAULT_TABLES)
    print(narrative)
