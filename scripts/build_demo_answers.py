"""Regenerates data/demo_answers.json by running each SQL against the Olist CSVs in DuckDB.

Every number in the file (result rows and insight text) comes from a query run
here; nothing is typed in by hand. Used by the app's demo mode when Gemini is
unavailable.

    python scripts/build_demo_answers.py
"""
import json
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parent.parent
OUTPUT = ROOT / "data" / "demo_answers.json"

TABLE_FILES = {
    "orders": "olist_orders_dataset.csv",
    "customers": "olist_customers_dataset.csv",
    "order_items": "olist_order_items_dataset.csv",
    "products": "olist_products_dataset.csv",
    "payments": "olist_order_payments_dataset.csv",
    "reviews": "olist_order_reviews_dataset.csv",
}

LATE = "o.order_delivered_customer_date > o.order_estimated_delivery_date"


def scalar(con, sql):
    return con.execute(sql).fetchone()[0]


def pretty(name):
    return name.replace("_", " ")


def insight_top_category(df, con):
    total = scalar(con, "SELECT SUM(price) FROM order_items")
    top = df.iloc[0]
    return (f"{pretty(top['category'])} is the top category with R$ {top['total_revenue']:,.0f} in item sales, "
            f"about {100 * top['total_revenue'] / total:.1f}% of all item revenue. "
            f"Revenue is spread across many categories rather than concentrated in one.")


def insight_delivery(df, con):
    avg = df.iloc[0, 0]
    est = scalar(con, "SELECT ROUND(AVG(date_diff('second', order_purchase_timestamp, "
                      "order_estimated_delivery_date) / 86400.0), 1) FROM orders "
                      "WHERE order_delivered_customer_date IS NOT NULL")
    return (f"Delivered orders take {avg} days on average from purchase to the customer's door. "
            f"That is faster than the {est}-day average promised at checkout, so Olist typically beats its own estimates.")


def insight_delayed_states(df, con):
    total_late = scalar(con, f"SELECT COUNT(*) FROM orders o WHERE {LATE}")
    top, second = df.iloc[0], df.iloc[1]
    return (f"{top['state']} has the most late deliveries ({top['delayed_orders']:,}), followed by "
            f"{second['state']} ({second['delayed_orders']:,}). Across all states {total_late:,} orders arrived after the estimated date, "
            f"and the largest markets naturally account for the biggest share of them.")


def insight_payment(df, con):
    total = df["payments"].sum()
    top = df.iloc[0]
    return (f"{pretty(top['payment_type']).title()} is the most common payment type with {top['payments']:,} payments, "
            f"{100 * top['payments'] / total:.1f}% of all {total:,}. "
            f"Boleto (a Brazilian bank slip) is the clear second choice with {df.iloc[1]['payments']:,}.")


def insight_low_reviews(df, con):
    n = df.iloc[0, 0]
    total = scalar(con, "SELECT COUNT(DISTINCT order_id) FROM reviews")
    return (f"{n:,} orders received a review score of 1 or 2, which is {100 * n / total:.1f}% of the {total:,} reviewed orders. "
            f"These unhappy customers are the natural starting point for improving delivery and product quality.")


def insight_top5_categories(df, con):
    total = scalar(con, "SELECT SUM(price) FROM order_items")
    share = 100 * df["total_revenue"].sum() / total
    return (f"The five biggest categories bring in R$ {df['total_revenue'].sum():,.0f} together, about {share:.1f}% of all item revenue. "
            f"{pretty(df.iloc[0]['category'])} leads, with {pretty(df.iloc[1]['category'])} close behind.")


def insight_total_revenue(df, con):
    orders = scalar(con, "SELECT COUNT(DISTINCT order_id) FROM payments")
    total = df.iloc[0, 0]
    return (f"Customers paid a total of R$ {total:,.0f} across {orders:,} paid orders. "
            f"That works out to about R$ {total / orders:,.0f} per order.")


def insight_avg_review(df, con):
    five = scalar(con, "SELECT COUNT(*) FROM reviews WHERE review_score = 5")
    total = scalar(con, "SELECT COUNT(*) FROM reviews")
    return (f"The average review score is {df.iloc[0, 0]} out of 5 across {total:,} reviews. "
            f"{100 * five / total:.1f}% of reviews are a perfect 5, so satisfaction is strong overall, with a tail of unhappy customers.")


def insight_late_orders(df, con):
    delivered = scalar(con, "SELECT COUNT(*) FROM orders WHERE order_delivered_customer_date IS NOT NULL")
    n = df.iloc[0, 0]
    return (f"{n:,} orders were delivered after the estimated date, about {100 * n / delivered:.1f}% of the {delivered:,} delivered orders. "
            f"In other words, the large majority of orders arrive on time or early.")


def insight_status(df, con):
    total = df["orders"].sum()
    top = df.iloc[0]
    canceled = df[df["order_status"] == "canceled"]["orders"].sum()
    return (f"{top['orders']:,} of {total:,} orders ({100 * top['orders'] / total:.1f}%) have been delivered. "
            f"Only {canceled:,} were canceled, so cancellations are a very small part of the business.")


# chart_type follows the app's own auto_chart rules: single value -> none,
# up to 8 rows -> pie, more -> bar, dates -> line.
ENTRIES = [
    ("Which product category had the highest total revenue?",
     """SELECT p.product_category_name AS category, ROUND(SUM(oi.price), 2) AS total_revenue
FROM order_items oi JOIN products p ON p.product_id = oi.product_id
WHERE p.product_category_name IS NOT NULL
GROUP BY category ORDER BY total_revenue DESC LIMIT 1""",
     "none", insight_top_category),
    ("What is the average delivery time in days?",
     """SELECT ROUND(AVG(date_diff('second', order_purchase_timestamp, order_delivered_customer_date) / 86400.0), 1) AS avg_delivery_days
FROM orders WHERE order_delivered_customer_date IS NOT NULL""",
     "none", insight_delivery),
    ("Which state has the most delayed deliveries?",
     f"""SELECT c.customer_state AS state, COUNT(*) AS delayed_orders
FROM orders o JOIN customers c ON c.customer_id = o.customer_id
WHERE {LATE}
GROUP BY state ORDER BY delayed_orders DESC LIMIT 5""",
     "pie", insight_delayed_states),
    ("What is the most common payment type?",
     """SELECT payment_type, COUNT(*) AS payments
FROM payments GROUP BY payment_type ORDER BY payments DESC""",
     "pie", insight_payment),
    ("How many orders have a review score of 1 or 2?",
     """SELECT COUNT(DISTINCT order_id) AS orders_with_low_score
FROM reviews WHERE review_score IN (1, 2)""",
     "none", insight_low_reviews),
    ("What are the top 5 product categories by total revenue?",
     """SELECT p.product_category_name AS category, ROUND(SUM(oi.price), 2) AS total_revenue
FROM order_items oi JOIN products p ON p.product_id = oi.product_id
WHERE p.product_category_name IS NOT NULL
GROUP BY category ORDER BY total_revenue DESC LIMIT 5""",
     "pie", insight_top5_categories),
    ("What is the total revenue from all orders?",
     "SELECT ROUND(SUM(payment_value), 2) AS total_revenue FROM payments",
     "none", insight_total_revenue),
    ("What is the average review score?",
     "SELECT ROUND(AVG(review_score), 2) AS avg_review_score FROM reviews",
     "none", insight_avg_review),
    ("How many orders were delivered late?",
     f"SELECT COUNT(*) AS late_orders FROM orders o WHERE {LATE}",
     "none", insight_late_orders),
    ("How many orders fall into each order status?",
     """SELECT order_status, COUNT(*) AS orders
FROM orders GROUP BY order_status ORDER BY orders DESC""",
     "pie", insight_status),
]


def to_json_value(v):
    return v.item() if hasattr(v, "item") else v


def build():
    con = duckdb.connect()  # in-memory: independent of olist.duckdb and of what users uploaded
    for table, filename in TABLE_FILES.items():
        path = (ROOT / "data" / filename).as_posix()
        con.execute(f"CREATE TABLE {table} AS SELECT * FROM read_csv_auto('{path}')")

    answers = []
    for question, sql, chart_type, insight_fn in ENTRIES:
        df = con.execute(sql).fetchdf()
        rows = [{k: to_json_value(v) for k, v in rec.items()} for rec in df.to_dict(orient="records")]
        answers.append({
            "question": question,
            "sql": sql,
            "result": rows,
            "chart_type": chart_type,
            "insight": insight_fn(df, con),
        })
    return answers


if __name__ == "__main__":
    answers = build()
    OUTPUT.write_text(json.dumps(answers, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Wrote {len(answers)} answers to {OUTPUT}")
