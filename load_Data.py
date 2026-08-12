import duckdb
con =duckdb.connect("olist.duckdb")

tables = {
    "orders":"data/olist_orders_dataset.csv",
    "customers":"data/olist_customers_dataset.csv",
    "order_items":"data/olist_order_items_dataset.csv",
    "products":"data/olist_products_dataset.csv",
    "payments":"data/olist_order_payments_dataset.csv",
    "reviews":"data/olist_order_reviews_dataset.csv",
}
for name, path in tables.items():
    con.execute(f"CREATE OR REPLACE TABLE {name} AS SELECT * FROM read_csv_auto('{path}')")
    print(name,"loaded:",con.execute(f"SELECT COUNT(*) FROM {name}").fetchone())

con.close()