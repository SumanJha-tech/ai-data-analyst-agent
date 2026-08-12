import duckdb
from google import genai
from dotenv import load_dotenv

load_dotenv()
client = genai.Client()
con = duckdb.connect("olist.duckdb")


def get_schema_from_db(con):
    """
    Automatically reads the table structure straight from DuckDB,
    instead of a human typing it out by hand.

    Why this matters: if you ever load a different dataset (different
    tables/columns), this function picks up the new structure automatically —
    nothing here needs to change except the CSV files you loaded.
    """
    tables = con.execute("SHOW TABLES").fetchdf()
    schema_text = ""
    for table in tables["name"]:
        columns = con.execute(f"DESCRIBE {table}").fetchdf()
        col_names = ", ".join(columns["column_name"])
        schema_text += f"{table}({col_names})\n"
    return schema_text


# Built once when this file is imported. Rebuilt automatically any time
# the app restarts, so it always reflects whatever is actually in the database.
SCHEMA = get_schema_from_db(con)


def clean_dataframe(df):
    """
    Basic missing-value cleanup applied to every result before it's shown
    or handed to Gemini for an insight.

    - Text/category columns: NaN becomes "Unknown" (e.g. Olist's real
      products table has some rows with a missing product_category_name —
      without this, they'd show up as blank/NaN in the table and chart).
    - Fully empty rows (every column NaN) are dropped — they add no
      information and would otherwise show up as a blank row.
    """
    df = df.copy()

    text_cols = df.select_dtypes(include="object").columns
    for col in text_cols:
        df[col] = df[col].fillna("Unknown")

    df = df.dropna(how="all")

    return df


def ask_question(question, max_retries=2):
    """
    Takes an English question, asks Gemini to write SQL for it,
    runs that SQL on DuckDB, and retries automatically if it fails.
    """
    error_feedback = ""  # will hold the error message if a retry is needed

    for attempt in range(max_retries + 1):
        prompt = f"""You are a SQL expert. Given this DuckDB schema:
{SCHEMA}

Write ONE SQL query (DuckDB syntax) to answer: "{question}"
Reply with ONLY the SQL query, no explanation, no markdown formatting.
{error_feedback}"""

        response = client.models.generate_content(
            model="gemini-3.6-flash",
            contents=prompt
        )

        # Gemini sometimes wraps SQL in ```sql ... ``` markdown blocks.
        # This cleans that up so we get pure SQL text.
        sql = response.text.strip().strip("`").replace("sql\n", "")

        try:
            result = con.execute(sql).fetchdf()
            result = clean_dataframe(result)  # handle missing values before returning
            return sql, result  # success! stop here and return the answer
        except Exception as e:
            print(f"Attempt {attempt + 1} failed: {e}")
            error_feedback = f"\nYour previous query failed with this error: {e}\nPlease fix it."

    raise Exception("Could not generate a working SQL query after retries.")


def validate_result(df):
    """
    Basic sanity checks on the result.
    Returns (is_valid, reason) — reason explains what's wrong if invalid.
    """
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
    """
    If the result has exactly 2 columns (label + number) and isn't too big,
    make a bar chart automatically.
    """
    import plotly.express as px

    if df.shape[1] == 2 and df.shape[0] <= 20:
        fig = px.bar(df, x=df.columns[0], y=df.columns[1])
        return fig

    return None


def generate_insight(question, df):
    """
    Asks Gemini to write a short, plain-English explanation of the result.
    """
    prompt = f"""The user asked: "{question}"
Here is the result data:
{df.to_string(index=False)}

Write a short 2-3 sentence business insight explaining what this shows. Be specific with numbers."""

    response = client.models.generate_content(
        model="gemini-3.6-flash",
        contents=prompt
    )
    return response.text.strip()


if __name__ == "__main__":
    print("--- Auto-detected schema ---")
    print(SCHEMA)

    questions = [
        "Which product category had the highest total revenue? Show the category and its revenue.",
        "What are the top 5 product categories by total revenue?",
    ]

    for question in questions:
        print("\n=================================================")
        print("Question:", question)

        sql, df = ask_question(question)

        print("\n--- SQL ---")
        print(sql)

        print("\n--- Result ---")
        print(df)

        is_valid, reason = validate_result(df)
        print("\n--- Validation ---")
        print(is_valid, "-", reason)

        fig = auto_chart(df)
        if fig:
            print("\n--- Chart ---")
            fig.show()
        else:
            print("\n--- Chart ---")
            print("No chart generated (data shape not suitable).")

        insight = generate_insight(question, df)
        print("\n--- Insight ---")
        print(insight)
