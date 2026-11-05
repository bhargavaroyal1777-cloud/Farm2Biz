"""Farm2Biz: direct produce marketplace with local SQLite or persistent PostgreSQL."""

from __future__ import annotations

import hashlib
import hmac
import html
import os
import secrets
import sqlite3
from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st


APP_DIR = Path(__file__).resolve().parent
DB_PATH = Path(os.environ.get("FARM2BIZ_DB", APP_DIR / "farm2biz.db"))
CATEGORIES = ["Vegetables", "Fruits", "Grains", "Dairy", "Herbs", "Other"]
UNITS = ["kg", "quintal", "tonne", "piece", "crate", "litre"]
GRADES = ["Grade A", "Grade B", "Grade C"]
GRADE_DETAILS = {
    "Grade A": "Premium quality: fresh, uniform, and carefully selected.",
    "Grade B": "Standard quality: good produce with minor natural variation.",
    "Grade C": "Value/processing grade: suitable for cooking or processing.",
}
STATUSES = ["Pending", "Accepted", "Rejected", "Ready for pickup", "In transit", "Completed", "Cancelled"]
DELIVERY_STATUSES = {"Ready for pickup", "In transit", "Completed"}
FALLBACK_EMOJI = {"Vegetables": "🥬", "Fruits": "🍎", "Grains": "🌾", "Dairy": "🥛", "Herbs": "🌿", "Other": "🧺"}

st.set_page_config(page_title="Farm2Biz", page_icon="🌾", layout="wide")


class PostgresConnection:
    """Small adapter that keeps the app's existing qmark SQL portable to PostgreSQL."""

    def __init__(self, url: str):
        import psycopg
        from psycopg.rows import dict_row

        self.raw = psycopg.connect(url, row_factory=dict_row, connect_timeout=15)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        try:
            if exc_type:
                self.raw.rollback()
            else:
                self.raw.commit()
        finally:
            self.raw.close()

    def execute(self, sql: str, params=()):
        return self.raw.execute(sql.replace("?", "%s"), params)


def configured_database_url() -> str | None:
    try:
        value = st.secrets.get("DATABASE_URL")
    except Exception:
        value = None
    return value or os.environ.get("DATABASE_URL") or None


def connect():
    url = configured_database_url()
    if url:
        return PostgresConnection(url)
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB_PATH, timeout=30, isolation_level="DEFERRED")
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    con.execute("PRAGMA busy_timeout = 30000")
    con.execute("PRAGMA synchronous = FULL")
    return con


def database_is_postgres() -> bool:
    return configured_database_url() is not None


def _sqlite_columns(con, table: str) -> set[str]:
    return {row["name"] for row in con.execute(f"PRAGMA table_info({table})").fetchall()}


def initialize_db() -> None:
    if database_is_postgres():
        with connect() as con:
            con.execute("""CREATE TABLE IF NOT EXISTS users (
                id BIGSERIAL PRIMARY KEY, name TEXT NOT NULL, email TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL, role TEXT NOT NULL CHECK(role IN ('Farmer','Buyer')),
                business TEXT NOT NULL DEFAULT '', location TEXT NOT NULL DEFAULT '',
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP)""")
            con.execute("""CREATE TABLE IF NOT EXISTS products (
                id BIGSERIAL PRIMARY KEY, farmer_id BIGINT NOT NULL REFERENCES users(id),
                name TEXT NOT NULL, category TEXT NOT NULL, description TEXT NOT NULL DEFAULT '',
                quantity DOUBLE PRECISION NOT NULL CHECK(quantity > 0), unit TEXT NOT NULL,
                price DOUBLE PRECISION NOT NULL CHECK(price >= 0), location TEXT NOT NULL DEFAULT '',
                available INTEGER NOT NULL DEFAULT 1, created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                grade TEXT NOT NULL DEFAULT 'Grade B', image_data BYTEA, image_mime TEXT)""")
            con.execute("""CREATE TABLE IF NOT EXISTS orders (
                id BIGSERIAL PRIMARY KEY, product_id BIGINT NOT NULL REFERENCES products(id),
                buyer_id BIGINT NOT NULL REFERENCES users(id), farmer_id BIGINT NOT NULL REFERENCES users(id),
                quantity DOUBLE PRECISION NOT NULL CHECK(quantity > 0), total DOUBLE PRECISION NOT NULL CHECK(total >= 0),
                status TEXT NOT NULL DEFAULT 'Pending', delivery_details TEXT NOT NULL DEFAULT '',
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP)""")
            con.execute("ALTER TABLE products ADD COLUMN IF NOT EXISTS grade TEXT NOT NULL DEFAULT 'Grade B'")
            con.execute("ALTER TABLE products ADD COLUMN IF NOT EXISTS image_data BYTEA")
            con.execute("ALTER TABLE products ADD COLUMN IF NOT EXISTS image_mime TEXT")
            _create_auxiliary_tables(con, postgres=True)
    else:
        with connect() as con:
            con.execute("PRAGMA journal_mode = WAL")
            con.execute("""CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL,
                email TEXT NOT NULL UNIQUE COLLATE NOCASE, password_hash TEXT NOT NULL,
                role TEXT NOT NULL CHECK(role IN ('Farmer', 'Buyer')),
                business TEXT NOT NULL DEFAULT '', location TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)""")
            con.execute("""CREATE TABLE IF NOT EXISTS products (
                id INTEGER PRIMARY KEY AUTOINCREMENT, farmer_id INTEGER NOT NULL REFERENCES users(id),
                name TEXT NOT NULL, category TEXT NOT NULL, description TEXT NOT NULL DEFAULT '',
                quantity REAL NOT NULL CHECK(quantity > 0), unit TEXT NOT NULL,
                price REAL NOT NULL CHECK(price >= 0), location TEXT NOT NULL DEFAULT '',
                available INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)""")
            con.execute("""CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT, product_id INTEGER NOT NULL REFERENCES products(id),
                buyer_id INTEGER NOT NULL REFERENCES users(id), farmer_id INTEGER NOT NULL REFERENCES users(id),
                quantity REAL NOT NULL CHECK(quantity > 0), total REAL NOT NULL CHECK(total >= 0),
                status TEXT NOT NULL DEFAULT 'Pending', delivery_details TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)""")
            # Additive migrations preserve all existing account, product, and order records.
            columns = _sqlite_columns(con, "products")
            if "grade" not in columns:
                con.execute("ALTER TABLE products ADD COLUMN grade TEXT NOT NULL DEFAULT 'Grade B'")
            if "image_data" not in columns:
                con.execute("ALTER TABLE products ADD COLUMN image_data BLOB")
            if "image_mime" not in columns:
                con.execute("ALTER TABLE products ADD COLUMN image_mime TEXT")
            _create_auxiliary_tables(con, postgres=False)


def _create_auxiliary_tables(con, postgres: bool) -> None:
    id_type = "BIGINT" if postgres else "INTEGER"
    con.execute(f"""CREATE TABLE IF NOT EXISTS notifications (
        id {'BIGSERIAL PRIMARY KEY' if postgres else 'INTEGER PRIMARY KEY AUTOINCREMENT'},
        user_id {id_type} NOT NULL REFERENCES users(id), order_id {id_type} REFERENCES orders(id),
        kind TEXT NOT NULL, message TEXT NOT NULL, is_read INTEGER NOT NULL DEFAULT 0,
        created_at {'TIMESTAMP' if postgres else 'TEXT'} NOT NULL DEFAULT CURRENT_TIMESTAMP)""")
    con.execute(f"""CREATE TABLE IF NOT EXISTS wishlist (
        buyer_id {id_type} NOT NULL REFERENCES users(id), product_id {id_type} NOT NULL REFERENCES products(id),
        created_at {'TIMESTAMP' if postgres else 'TEXT'} NOT NULL DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY(buyer_id, product_id))""")
    con.execute(f"""CREATE TABLE IF NOT EXISTS price_history (
        id {'BIGSERIAL PRIMARY KEY' if postgres else 'INTEGER PRIMARY KEY AUTOINCREMENT'},
        product_id {id_type} NOT NULL REFERENCES products(id), farmer_id {id_type} NOT NULL REFERENCES users(id),
        category TEXT NOT NULL, price DOUBLE PRECISION NOT NULL, unit TEXT NOT NULL,
        observed_at {'TIMESTAMP' if postgres else 'TEXT'} NOT NULL DEFAULT CURRENT_TIMESTAMP)""")
    con.execute("CREATE INDEX IF NOT EXISTS idx_orders_farmer_status ON orders(farmer_id, status)")
    con.execute("CREATE INDEX IF NOT EXISTS idx_orders_buyer_status ON orders(buyer_id, status)")
    con.execute("CREATE INDEX IF NOT EXISTS idx_notifications_user_read ON notifications(user_id, is_read)")
    con.execute("CREATE INDEX IF NOT EXISTS idx_price_history_product_date ON price_history(product_id, observed_at)")


def password_digest(password: str, salt: bytes | None = None) -> str:
    salt = salt or secrets.token_bytes(16)
    derived = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 310_000)
    return f"{salt.hex()}:{derived.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        salt_hex, expected = stored.split(":", 1)
        actual = password_digest(password, bytes.fromhex(salt_hex)).split(":", 1)[1]
        return hmac.compare_digest(actual, expected)
    except (ValueError, TypeError):
        return False


def current_user() -> dict | None:
    return st.session_state.get("user")


def register(name: str, email: str, password: str, role: str, business: str, location: str) -> None:
    with connect() as con:
        con.execute("INSERT INTO users(name,email,password_hash,role,business,location) VALUES(?,?,?,?,?,?)",
                    (name.strip(), email.strip().lower(), password_digest(password), role, business.strip(), location.strip()))


def login(email: str, password: str) -> dict | None:
    with connect() as con:
        row = con.execute("SELECT * FROM users WHERE email = ?", (email.strip().lower(),)).fetchone()
    if row and verify_password(password, row["password_hash"]):
        return dict(row)
    return None


def money(value: float) -> str:
    return f"₹{value:,.2f}"


def notify(con, user_id: int, order_id: int | None, kind: str, message: str) -> None:
    con.execute("INSERT INTO notifications(user_id,order_id,kind,message) VALUES(?,?,?,?)",
                (user_id, order_id, kind, message))


def record_price(con, product_id: int, farmer_id: int, category: str, price: float, unit: str) -> None:
    con.execute("INSERT INTO price_history(product_id,farmer_id,category,price,unit) VALUES(?,?,?,?,?)",
                (product_id, farmer_id, category, price, unit))


def auth_screen() -> None:
    st.markdown("# 🌾 Farm2Biz")
    st.caption("Fresh produce, direct from farms to businesses")
    login_tab, register_tab = st.tabs(["Sign in", "Create account"])
    with login_tab:
        with st.form("login"):
            email = st.text_input("Email", key="login_email")
            password = st.text_input("Password", type="password", key="login_password")
            submitted = st.form_submit_button("Sign in", type="primary")
        if submitted:
            user = login(email, password)
            if user:
                st.session_state.user = user
                st.rerun()
            st.error("Email or password is incorrect.")
    with register_tab:
        with st.form("register"):
            role = st.selectbox("I am a", ["Farmer", "Buyer"])
            name = st.text_input("Your name")
            email = st.text_input("Email address")
            business = st.text_input("Business name (buyers)") if role == "Buyer" else ""
            location = st.text_input("Village, town, or city")
            password = st.text_input("Password", type="password", help="Use at least 8 characters.")
            confirm = st.text_input("Confirm password", type="password")
            submitted = st.form_submit_button("Create account", type="primary")
        if submitted:
            if not name.strip() or not email.strip() or not location.strip():
                st.error("Please complete your name, email, and location.")
            elif len(password) < 8:
                st.error("Use a password with at least 8 characters.")
            elif password != confirm:
                st.error("The passwords do not match.")
            else:
                try:
                    register(name, email, password, role, business, location)
                    st.success("Account created. Sign in to continue.")
                except Exception:
                    st.error("An account with that email may already exist.")


def add_product(user: dict) -> None:
    st.subheader("List a product")
    with st.form("new_product", clear_on_submit=True):
        a, b = st.columns(2)
        name = a.text_input("Product name")
        category = b.selectbox("Category", CATEGORIES)
        description = st.text_area("Description / harvest and quality notes")
        c1, c2, c3 = st.columns(3)
        quantity = c1.number_input("Available quantity", min_value=0.1, value=10.0, step=1.0)
        unit = c2.selectbox("Unit", UNITS)
        price = c3.number_input("Price per unit (₹)", min_value=0.0, value=0.0, step=1.0)
        grade = st.selectbox("Quality grade", GRADES, index=1, help=GRADE_DETAILS["Grade B"])
        location = st.text_input("Pickup location", value=user.get("location", ""))
        image_file = st.file_uploader("Product photo (optional, JPG/PNG/WebP, max 2 MB)", type=["jpg", "jpeg", "png", "webp"])
        save = st.form_submit_button("Publish listing", type="primary")
    if save:
        if not name.strip() or price <= 0 or not location.strip():
            st.error("Enter a product name, price above zero, and pickup location.")
            return
        image_data, image_mime = None, None
        if image_file:
            if image_file.size > 2 * 1024 * 1024:
                st.error("Image must be 2 MB or smaller.")
                return
            image_data, image_mime = image_file.getvalue(), image_file.type
        with connect() as con:
            if database_is_postgres():
                row = con.execute("""INSERT INTO products(farmer_id,name,category,description,quantity,unit,price,location,grade,image_data,image_mime)
                    VALUES(?,?,?,?,?,?,?,?,?,?,?) RETURNING id""",
                    (user["id"], name.strip(), category, description.strip(), quantity, unit, price, location.strip(), grade, image_data, image_mime)).fetchone()
                product_id = row["id"]
            else:
                cur = con.execute("""INSERT INTO products(farmer_id,name,category,description,quantity,unit,price,location,grade,image_data,image_mime)
                    VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                    (user["id"], name.strip(), category, description.strip(), quantity, unit, price, location.strip(), grade, image_data, image_mime))
                product_id = cur.lastrowid
            record_price(con, product_id, user["id"], category, price, unit)
        st.success("Your product is now listed.")
        st.rerun()


def toggle_wishlist(user_id: int, product_id: int) -> None:
    with connect() as con:
        exists = con.execute("SELECT 1 FROM wishlist WHERE buyer_id=? AND product_id=?", (user_id, product_id)).fetchone()
        if exists:
            con.execute("DELETE FROM wishlist WHERE buyer_id=? AND product_id=?", (user_id, product_id))
        else:
            con.execute("INSERT INTO wishlist(buyer_id,product_id) VALUES(?,?) ON CONFLICT(buyer_id,product_id) DO NOTHING",
                        (user_id, product_id))


def place_order(product_id: int, buyer: dict, quantity: float, delivery: str) -> tuple[bool, str]:
    """Reserve inventory and insert order atomically to prevent overselling."""
    with connect() as con:
        if not database_is_postgres():
            con.execute("BEGIN IMMEDIATE")
        product = con.execute("SELECT id,farmer_id,name,quantity,price,unit FROM products WHERE id=? AND available=1" +
                              (" FOR UPDATE" if database_is_postgres() else ""), (product_id,)).fetchone()
        if not product or quantity <= 0 or quantity > product["quantity"]:
            return False, "Available quantity changed. Refresh the page and try again."
        new_quantity = con.execute("UPDATE products SET quantity=quantity-? WHERE id=? AND available=1 AND quantity>=?",
                                   (quantity, product_id, quantity))
        if new_quantity.rowcount != 1:
            return False, "This quantity is no longer available. Refresh and try again."
        total = quantity * product["price"]
        if database_is_postgres():
            row = con.execute("""INSERT INTO orders(product_id,buyer_id,farmer_id,quantity,total,delivery_details)
                VALUES(?,?,?,?,?,?) RETURNING id""",
                (product_id, buyer["id"], product["farmer_id"], quantity, total, delivery.strip())).fetchone()
            order_id = row["id"]
        else:
            order_id = con.execute("""INSERT INTO orders(product_id,buyer_id,farmer_id,quantity,total,delivery_details)
                VALUES(?,?,?,?,?,?)""", (product_id, buyer["id"], product["farmer_id"], quantity, total, delivery.strip())).lastrowid
        notify(con, product["farmer_id"], order_id, "New order", f"New order for {quantity:g} {product['unit']} of {product['name']}.")
    return True, "Order sent to the farmer."


def change_order_status(order_id: int, farmer_id: int, new_status: str) -> bool:
    with connect() as con:
        order = con.execute("""SELECT o.status,o.buyer_id,o.product_id,o.quantity,p.name FROM orders o JOIN products p ON p.id=o.product_id
            WHERE o.id=? AND o.farmer_id=?""", (order_id, farmer_id)).fetchone()
        if not order or order["status"] == new_status:
            return False
        allowed = {
            "Pending": {"Accepted", "Rejected", "Cancelled"},
            "Accepted": {"Ready for pickup", "In transit", "Completed", "Rejected", "Cancelled"},
            "Ready for pickup": {"In transit", "Completed", "Cancelled"},
            "In transit": {"Completed"}, "Completed": set(), "Rejected": set(), "Cancelled": set(),
        }
        if new_status not in allowed.get(order["status"], set()):
            return False
        cur = con.execute("UPDATE orders SET status=? WHERE id=? AND farmer_id=?", (new_status, order_id, farmer_id))
        if cur.rowcount != 1:
            return False
        if new_status in {"Rejected", "Cancelled"} and order["status"] in {"Pending", "Accepted", "Ready for pickup"}:
            con.execute("UPDATE products SET quantity=quantity+? WHERE id=?", (order["quantity"], order["product_id"]))
        if new_status == "Accepted":
            kind, message = "Order accepted", f"Your order for {order['name']} was accepted by the farmer."
        elif new_status == "Rejected":
            kind, message = "Order rejected", f"Your order for {order['name']} was rejected by the farmer."
        elif new_status in DELIVERY_STATUSES:
            kind, message = "Delivery update", f"Order update for {order['name']}: {new_status}."
        else:
            kind, message = "Order update", f"Your order for {order['name']} is now {new_status.lower()}."
        notify(con, order["buyer_id"], order_id, kind, message)
    return True


def product_image(product: dict) -> None:
    if product.get("image_data"):
        st.image(product["image_data"], use_container_width=True)
    else:
        emoji = FALLBACK_EMOJI.get(product["category"], "🧺")
        st.markdown(f'<div class="produce-art"><span>{emoji}</span><small>{product["category"]} · Farm fresh</small></div>', unsafe_allow_html=True)


def product_card(product: dict, user: dict, show_order: bool = True, wishlist_view: bool = False) -> None:
    product = dict(product)
    with st.container(border=True):
        image_col, info_col, price_col = st.columns([1.1, 3.4, 1.3])
        with image_col:
            product_image(product)
        with info_col:
            safe_name = html.escape(str(product["name"]))
            safe_grade = html.escape(str(product.get("grade", "Grade B")))
            st.markdown(f"### {safe_name} <span class='grade-badge'>{safe_grade}</span>", unsafe_allow_html=True)
            st.caption(f"{product['category']} · {GRADE_DETAILS.get(product.get('grade', 'Grade B'), GRADE_DETAILS['Grade B'])}")
            st.write(product.get("description") or "Fresh produce available for direct purchase.")
            st.caption(f"Farmer: {product['farmer_name']} · Pickup: {product['location']} · Listed: {str(product['created_at'])[:10]}")
        with price_col:
            st.metric("Price", f"{money(product['price'])} / {product['unit']}")
            st.write(f"Available: **{product['quantity']:g} {product['unit']}**")
            if user["role"] == "Buyer":
                wish_key = f"wish_{product['id']}_{'saved' if wishlist_view else 'market'}"
                with connect() as con:
                    saved = con.execute("SELECT 1 FROM wishlist WHERE buyer_id=? AND product_id=?", (user["id"], product["id"])).fetchone()
                if st.button("♥ Saved" if saved else "♡ Wishlist", key=wish_key, use_container_width=True):
                    toggle_wishlist(user["id"], product["id"])
                    st.rerun()
        if show_order and user["role"] == "Buyer" and product["quantity"] > 0:
            with st.form(f"order_{product['id']}"):
                q_col, d_col, button_col = st.columns([1, 2.5, 1])
                qty = q_col.number_input("Order quantity", min_value=0.1, max_value=float(product["quantity"]),
                                         value=min(1.0, float(product["quantity"])), step=0.1, key=f"qty_{product['id']}")
                delivery = d_col.text_input("Delivery / transport request", key=f"delivery_{product['id']}")
                place = button_col.form_submit_button("Place order", type="primary")
            if place:
                ok, message = place_order(product["id"], user, qty, delivery)
                (st.success if ok else st.error)(message)
                if ok:
                    st.rerun()
        elif user["role"] == "Farmer" and user["id"] == product["farmer_id"]:
            st.caption("Your listing · Manage it under My products.")


def marketplace(user: dict) -> None:
    st.subheader("Fresh produce marketplace")
    with connect() as con:
        source = con.execute("SELECT p.*,u.name AS farmer_name,u.location AS farmer_location FROM products p JOIN users u ON u.id=p.farmer_id WHERE p.available=1 AND p.quantity>0 ORDER BY p.created_at DESC").fetchall()
    if not source:
        st.info("No products listed yet. Farmers can add the first listing.")
        return
    products = [dict(row) for row in source]
    max_price = max(float(p["price"]) for p in products)
    min_price = min(float(p["price"]) for p in products)
    a, b, c = st.columns([1.5, 1, 1])
    query = a.text_input("Search product or farmer", placeholder="Tomato, farmer name")
    category = b.selectbox("Category", ["All categories", *CATEGORIES])
    grade = c.selectbox("Quality grade", ["All grades", *GRADES])
    d, e, f = st.columns([1.4, 1, 1])
    location = d.text_input("Filter by location", placeholder="Village, town, or city")
    low = e.number_input("Min price (₹)", min_value=0.0, max_value=max_price, value=min_price, step=1.0)
    high = f.number_input("Max price (₹)", min_value=0.0, value=max_price, step=1.0)
    if high < low:
        st.warning("Maximum price must be at least the minimum price.")
        return
    sort = st.selectbox("Sort listings", ["Newest", "Price: low to high", "Price: high to low"])
    clauses = ["p.available=1", "p.quantity>0", "p.price>=?", "p.price<=?"]
    args: list = [low, high]
    if query.strip():
        clauses.append("(p.name LIKE ? OR u.name LIKE ?)")
        args.extend([f"%{query.strip()}%"] * 2)
    if location.strip():
        clauses.append("(p.location LIKE ? OR u.location LIKE ?)")
        args.extend([f"%{location.strip()}%"] * 2)
    if category != "All categories":
        clauses.append("p.category=?")
        args.append(category)
    if grade != "All grades":
        clauses.append("p.grade=?")
        args.append(grade)
    order_clause = {"Newest": "p.created_at DESC", "Price: low to high": "p.price ASC", "Price: high to low": "p.price DESC"}[sort]
    sql = "SELECT p.*,u.name AS farmer_name,u.location AS farmer_location FROM products p JOIN users u ON u.id=p.farmer_id WHERE " + " AND ".join(clauses) + " ORDER BY " + order_clause
    with connect() as con:
        rows = con.execute(sql, args).fetchall()
    st.caption(f"{len(rows)} listing(s) match your filters")
    if not rows:
        st.info("No matching products. Adjust your filters and try again.")
        return
    for product in rows:
        product_card(dict(product), user)


def dashboard(user: dict) -> None:
    st.subheader("Marketplace overview")
    with connect() as con:
        counts = con.execute("""SELECT
            (SELECT COUNT(*) FROM users WHERE role='Farmer') AS farmers,
            (SELECT COUNT(*) FROM users WHERE role='Buyer') AS buyers,
            (SELECT COUNT(*) FROM products) AS products,
            (SELECT COUNT(*) FROM orders) AS orders,
            (SELECT COALESCE(SUM(total),0) FROM orders WHERE status='Completed') AS sales,
            (SELECT COUNT(*) FROM orders WHERE status='Pending') AS pending""").fetchone()
        status_rows = con.execute("SELECT status,COUNT(*) AS n FROM orders GROUP BY status ORDER BY n DESC").fetchall()
        sales_rows = con.execute("SELECT created_at,total FROM orders WHERE status='Completed' ORDER BY created_at").fetchall()
    values = [("👩🏽‍🌾 Farmers", counts["farmers"]), ("🏪 Buyers", counts["buyers"]),
        ("🥬 Products", counts["products"]), ("📦 Orders", counts["orders"]),
              ("💰 Completed sales", money(counts["sales"])), ("⏳ Pending orders", counts["pending"])]
    for start in range(0, len(values), 3):
        cols = st.columns(3)
        for col, (label, value) in zip(cols, values[start:start + 3]):
            col.metric(label, value)
    chart_left, chart_right = st.columns(2)
    with chart_left:
        st.markdown("#### Orders by status")
        if status_rows:
            st.bar_chart(pd.DataFrame({"Orders": [row["n"] for row in status_rows]}, index=[row["status"] for row in status_rows]), color="#2f855a")
        else:
            st.caption("Order activity will appear here.")
    with chart_right:
        st.markdown("#### Completed sales trend")
        monthly: dict[str, float] = {}
        for row in sales_rows:
            key = str(row["created_at"])[:7]
            monthly[key] = monthly.get(key, 0.0) + float(row["total"])
        if len(monthly) >= 2:
            st.line_chart(pd.DataFrame({"Month": list(monthly.keys()), "Sales (₹)": list(monthly.values())}).set_index("Month"), color="#2f855a")
        else:
            st.info("Price/sales trends appear after enough real transactions are recorded.")
    st.divider()
    if user["role"] == "Farmer":
        farmer_analytics(user)
    else:
        buyer_analytics(user)


def farmer_analytics(user: dict) -> None:
    st.markdown("### Your farm analytics")
    with connect() as con:
        row = con.execute("""SELECT
            COALESCE(SUM(CASE WHEN status='Completed' THEN total ELSE 0 END),0) AS earnings,
            COUNT(CASE WHEN status='Completed' THEN 1 END) AS completed,
            COALESCE((SELECT SUM(quantity) FROM products WHERE farmer_id=? AND available=1),0) AS stock,
            COUNT(*) AS all_orders
            FROM orders WHERE farmer_id=?""", (user["id"], user["id"])).fetchone()
        stock_rows = con.execute("SELECT name,quantity,unit FROM products WHERE farmer_id=? AND available=1 ORDER BY quantity DESC", (user["id"],)).fetchall()
    a, b, c, d = st.columns(4)
    a.metric("Completed sales", money(row["earnings"]))
    stock_summary: dict[str, float] = {}
    for product in stock_rows:
        stock_summary[product["unit"]] = stock_summary.get(product["unit"], 0.0) + product["quantity"]
    stock_label = " · ".join(f"{amount:g} {unit}" for unit, amount in stock_summary.items()) or "0"
    b.metric("Available stock", stock_label)
    c.metric("Completed orders", row["completed"])
    d.metric("Total orders", row["all_orders"])
    if stock_rows:
        st.markdown("#### Available stock by product")
        st.bar_chart(pd.DataFrame({"Quantity": [p["quantity"] for p in stock_rows]}, index=[p["name"] for p in stock_rows]), color="#66a182")


def buyer_analytics(user: dict) -> None:
    st.markdown("### Your buyer analytics")
    with connect() as con:
        row = con.execute("""SELECT
            COALESCE(SUM(CASE WHEN status='Completed' THEN total ELSE 0 END),0) AS spending,
            COUNT(CASE WHEN status IN ('Pending','Accepted','Ready for pickup','In transit') THEN 1 END) AS active,
            COUNT(*) AS total_orders FROM orders WHERE buyer_id=?""", (user["id"],)).fetchone()
        history = con.execute("""SELECT o.id,p.name AS product_name,o.quantity,p.unit,o.total,o.status,o.created_at
            FROM orders o JOIN products p ON p.id=o.product_id WHERE o.buyer_id=? ORDER BY o.created_at DESC LIMIT 20""", (user["id"],)).fetchall()
    a, b, c = st.columns(3)
    a.metric("Completed spending", money(row["spending"]))
    b.metric("Active orders", row["active"])
    c.metric("Purchase count", row["total_orders"])
    if history:
        st.markdown("#### Recent purchase history")
        st.dataframe([dict(item) for item in history], use_container_width=True, hide_index=True)
    else:
        st.caption("Your purchase history will appear after you place an order.")


def products_page(user: dict) -> None:
    st.subheader("My products")
    with connect() as con:
        products = con.execute("SELECT * FROM products WHERE farmer_id=? ORDER BY created_at DESC", (user["id"],)).fetchall()
    if not products:
        st.info("You have not listed any products yet.")
        return
    for item in products:
        p = dict(item)
        with st.container(border=True):
            a, b = st.columns([3, 1])
            a.markdown(f"### {p['name']} · {p['grade']}")
            a.write(f"{p['quantity']:g} {p['unit']} available · {money(p['price'])}/{p['unit']} · {p['location']}")
            with b:
                active = st.toggle("Available", value=bool(p["available"]), key=f"active_{p['id']}")
                if active != bool(p["available"]):
                    with connect() as con:
                        con.execute("UPDATE products SET available=? WHERE id=? AND farmer_id=?", (int(active), p["id"], user["id"]))
                    st.rerun()
            with st.expander("Edit price, grade, or product details"):
                with st.form(f"edit_product_{p['id']}"):
                    new_name = st.text_input("Product name", value=p["name"], key=f"name_{p['id']}")
                    new_price = st.number_input("Price per unit (₹)", min_value=0.01, value=float(p["price"]), step=1.0, key=f"price_{p['id']}")
                    new_grade = st.selectbox("Quality grade", GRADES, index=GRADES.index(p.get("grade", "Grade B")), key=f"grade_{p['id']}")
                    new_description = st.text_area("Description", value=p["description"], key=f"desc_{p['id']}")
                    replacement = st.file_uploader("Replace product photo (optional)", type=["jpg", "jpeg", "png", "webp"], key=f"photo_{p['id']}")
                    save = st.form_submit_button("Save product changes")
                if save:
                    if replacement and replacement.size > 2 * 1024 * 1024:
                        st.error("Image must be 2 MB or smaller.")
                    else:
                        with connect() as con:
                            if replacement:
                                con.execute("UPDATE products SET name=?,price=?,grade=?,description=?,image_data=?,image_mime=? WHERE id=? AND farmer_id=?",
                                            (new_name.strip(), new_price, new_grade, new_description.strip(), replacement.getvalue(), replacement.type, p["id"], user["id"]))
                            else:
                                con.execute("UPDATE products SET name=?,price=?,grade=?,description=? WHERE id=? AND farmer_id=?",
                                            (new_name.strip(), new_price, new_grade, new_description.strip(), p["id"], user["id"]))
                            if new_price != p["price"]:
                                record_price(con, p["id"], user["id"], p["category"], new_price, p["unit"])
                        st.success("Product updated.")
                        st.rerun()


def wishlist_page(user: dict) -> None:
    st.subheader("Your saved products")
    with connect() as con:
        rows = con.execute("""SELECT p.*,u.name AS farmer_name,u.location AS farmer_location
            FROM wishlist w JOIN products p ON p.id=w.product_id JOIN users u ON u.id=p.farmer_id
            WHERE w.buyer_id=? AND p.available=1 ORDER BY w.created_at DESC""", (user["id"],)).fetchall()
    if not rows:
        st.info("No saved products yet. Use the ♡ Wishlist button in the marketplace.")
        return
    for row in rows:
        product_card(dict(row), user, show_order=True, wishlist_view=True)


def notifications_page(user: dict) -> None:
    st.subheader("Notifications")
    with connect() as con:
        rows = con.execute("SELECT * FROM notifications WHERE user_id=? ORDER BY created_at DESC LIMIT 100", (user["id"],)).fetchall()
    if not rows:
        st.info("Order and delivery updates will appear here.")
        return
    unread = [r for r in rows if not r["is_read"]]
    if unread and st.button("Mark all as read"):
        with connect() as con:
            con.execute("UPDATE notifications SET is_read=1 WHERE user_id=?", (user["id"],))
        st.rerun()
    for row in rows:
        icon = "🔔" if not row["is_read"] else "✓"
        with st.container(border=True):
            st.markdown(f"**{icon} {row['kind']}** · {str(row['created_at'])[:16]}")
            st.write(row["message"])


def price_insights() -> None:
    st.subheader("Price insights")
    with connect() as con:
        history = con.execute("SELECT category,unit,price,observed_at FROM price_history ORDER BY observed_at").fetchall()
        comparison = con.execute("""SELECT category,unit,AVG(price) AS average_price,MIN(price) AS low_price,MAX(price) AS high_price,COUNT(*) AS samples
            FROM products WHERE available=1 GROUP BY category,unit ORDER BY category,unit""").fetchall()
    if comparison:
        st.markdown("#### Current market price comparison")
        st.dataframe([{"Category": r["category"], "Unit": r["unit"], "Average": money(r["average_price"]),
                       "Range": f"{money(r['low_price'])} – {money(r['high_price'])}", "Listings": r["samples"]} for r in comparison],
                     use_container_width=True, hide_index=True)
    if len(history) >= 2:
        df = pd.DataFrame([dict(r) for r in history])
        df["observed_at"] = pd.to_datetime(df["observed_at"], errors="coerce")
        df = df.dropna(subset=["observed_at"])
        if len(df) >= 2:
            trend = df.groupby([pd.Grouper(key="observed_at", freq="D"), "category", "unit"], as_index=False)["price"].mean()
            st.markdown("#### Observed listing price history")
            category_options = sorted(trend["category"].unique().tolist())
            chosen = st.selectbox("Trend category", category_options)
            selected = trend[trend["category"] == chosen]
            if len(selected) >= 2:
                st.line_chart(selected.pivot(index="observed_at", columns="unit", values="price"), color="#2f855a")
            else:
                st.info("This category needs at least two real price observations on different dates for a trend line.")
        else:
            st.info("Price history needs multiple real observations to show a trend.")
    else:
        st.info("Price trends appear after farmers create or update listings over time. No sample transactions are added.")


def apply_theme() -> None:
    st.markdown("""
    <style>
      :root { --farm-green:#236b45; --farm-light:#edf7ef; --farm-ink:#193b2a; }
      .stApp { background:linear-gradient(180deg,#f8fcf8 0%,#ffffff 260px); color:var(--farm-ink); }
      [data-testid="stSidebar"] { background:#eff7f0; border-right:1px solid #d8e9db; }
      [data-testid="stSidebar"] [data-testid="stMarkdownContainer"] p { color:#244d34; }
      h1,h2,h3 { color:#194d32; letter-spacing:-.02em; }
      [data-testid="stMetric"] { background:#fff; border:1px solid #dceade; border-radius:16px; padding:16px 18px; box-shadow:0 4px 16px rgba(35,107,69,.06); }
      [data-testid="stMetricValue"] { color:#236b45; }
      .stButton > button[kind="primary"], .stFormSubmitButton > button[kind="primary"] { background:#236b45; border-color:#236b45; }
      .stButton > button:hover, .stFormSubmitButton > button:hover { border-color:#236b45; color:#236b45; }
      [data-testid="stVerticalBlockBorderWrapper"] { border-color:#d8e9db; border-radius:16px; }
      .produce-art { height:150px; border-radius:14px; background:linear-gradient(140deg,#e6f4df,#f8f5d9 70%,#e2f0e5); display:flex; flex-direction:column; align-items:center; justify-content:center; color:#236b45; }
      .produce-art span { font-size:54px; line-height:1.1; }
      .produce-art small { margin-top:10px; font-size:12px; color:#567361; }
      .grade-badge { display:inline-block; vertical-align:middle; font-size:12px; border-radius:999px; padding:4px 10px; color:#236b45; background:#e8f4e9; border:1px solid #c9e2ce; }
      @media (max-width: 760px) { .produce-art { height:110px; } }
    </style>
    """, unsafe_allow_html=True)


def verify_db_integrity() -> tuple[bool, str]:
    if database_is_postgres():
        with connect() as con:
            con.execute("SELECT 1").fetchone()
        return True, "Database connection and constraints are active."
    with connect() as con:
        result = con.execute("PRAGMA quick_check").fetchone()[0]
        foreign_key_issues = con.execute("PRAGMA foreign_key_check").fetchall()
    if result != "ok" or foreign_key_issues:
        return False, "Database integrity check reported an issue. Stop writes and restore from a known good database backup."
    return True, "SQLite integrity and foreign-key checks passed."


def main() -> None:
    initialize_db()
    apply_theme()
    if not st.session_state.get("farm2biz_integrity_checked"):
        valid, integrity_message = verify_db_integrity()
        if not valid:
            st.error(integrity_message)
            st.stop()
        st.session_state.farm2biz_integrity_checked = True
    if not current_user():
        auth_screen()
        return
    user = current_user()
    with connect() as con:
        unread_count = con.execute("SELECT COUNT(*) AS n FROM notifications WHERE user_id=? AND is_read=0", (user["id"],)).fetchone()["n"]
    with st.sidebar:
        st.markdown("## 🌾 Farm2Biz")
        st.write(f"**{user['name']}**")
        st.caption(f"{user['role']} · {user['location']}")
        if database_is_postgres():
            st.caption("Storage: PostgreSQL · durable backend")
        else:
            st.caption("Storage: SQLite · local file; hosted deployments need DATABASE_URL for durable data")
        if st.button("Sign out", use_container_width=True):
            st.session_state.pop("user", None)
            st.rerun()
        st.divider()
        nav_options = ["📊 Dashboard", "🛒 Marketplace", "🔔 Notifications"]
        if user["role"] == "Farmer":
            nav_options += ["🌱 My products", "📈 Price insights", "📦 Orders"]
        else:
            nav_options += ["♡ Wishlist", "📈 Price insights", "📦 Orders"]
        page = st.radio("Navigate", nav_options, label_visibility="collapsed", format_func=lambda x: f"{x}  ({unread_count})" if x == "🔔 Notifications" and unread_count else x)
    page_title = {"📊 Dashboard": "Farm2Biz dashboard", "🛒 Marketplace": "Find fresh produce",
                  "🌱 My products": "Manage your listings", "📈 Price insights": "Price insights",
                  "♡ Wishlist": "Your wishlist", "🔔 Notifications": "Notifications", "📦 Orders": "Track your orders"}
    st.title(page_title[page])
    st.caption("Direct produce trading between local farmers and business buyers.")
    if page == "📊 Dashboard":
        dashboard(user)
    elif page == "🛒 Marketplace":
        if user["role"] == "Farmer":
            with st.expander("＋ List a product", expanded=False):
                add_product(user)
        marketplace(user)
    elif page == "🌱 My products":
        products_page(user)
    elif page == "📈 Price insights":
        price_insights()
    elif page == "♡ Wishlist":
        wishlist_page(user)
    elif page == "🔔 Notifications":
        notifications_page(user)
    else:
        order_page(user)


def order_page(user: dict) -> None:
    st.subheader("Orders")
    field, other_user_field = ("farmer_id", "buyer_id") if user["role"] == "Farmer" else ("buyer_id", "farmer_id")
    with connect() as con:
        orders = con.execute(f"""SELECT o.*,p.name AS product_name,p.unit,u.name AS other_name,u.business AS other_business
            FROM orders o JOIN products p ON p.id=o.product_id JOIN users u ON u.id=o.{other_user_field}
            WHERE o.{field}=? ORDER BY o.created_at DESC""", (user["id"],)).fetchall()
    if not orders:
        st.info("Your orders will appear here.")
        return
    for order in orders:
        with st.container(border=True):
            a, b = st.columns([3, 1])
            a.markdown(f"**Order #{order['id']} · {order['product_name']}**")
            counterparty = order["other_business"] or order["other_name"]
            a.write(f"{order['quantity']:g} {order['unit']} · {money(order['total'])} · {str(order['created_at'])[:16]}")
            a.write(f"{'Buyer' if user['role']=='Farmer' else 'Farmer'}: {counterparty}")
            a.write(f"Delivery: {order['delivery_details'] or 'To be arranged'}")
            if user["role"] == "Farmer":
                with b.form(f"status_{order['id']}"):
                    allowed = {
                        "Pending": ["Pending", "Accepted", "Rejected", "Cancelled"],
                        "Accepted": ["Accepted", "Ready for pickup", "In transit", "Completed", "Rejected", "Cancelled"],
                        "Ready for pickup": ["Ready for pickup", "In transit", "Completed", "Cancelled"],
                        "In transit": ["In transit", "Completed"],
                        "Completed": ["Completed"], "Rejected": ["Rejected"], "Cancelled": ["Cancelled"],
                    }.get(order["status"], [order["status"]])
                    new_status = st.selectbox("Status", allowed, key=f"status_pick_{order['id']}")
                    if st.form_submit_button("Update status") and new_status != order["status"]:
                        change_order_status(order["id"], user["id"], new_status)
                        st.rerun()
            else:
                b.metric("Status", order["status"])


if __name__ == "__main__":
    main()
