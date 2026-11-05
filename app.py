"""Farm2Biz: a small farm-to-business marketplace built with Streamlit and SQLite."""

from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import sqlite3
from datetime import date
from pathlib import Path

import streamlit as st


APP_DIR = Path(__file__).resolve().parent
DB_PATH = Path(os.environ.get("FARM2BIZ_DB", APP_DIR / "farm2biz.db"))
CATEGORIES = ["Vegetables", "Fruits", "Grains", "Dairy", "Herbs", "Other"]
UNITS = ["kg", "quintal", "tonne", "piece", "crate", "litre"]
STATUSES = ["Pending", "Accepted", "Ready for pickup", "In transit", "Completed", "Cancelled"]

st.set_page_config(page_title="Farm2Biz", page_icon="🌾", layout="wide")


def connect() -> sqlite3.Connection:
    con = sqlite3.connect(DB_PATH, timeout=15)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    return con


def initialize_db() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with connect() as con:
        con.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                email TEXT NOT NULL UNIQUE COLLATE NOCASE,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL CHECK(role IN ('Farmer', 'Buyer')),
                business TEXT NOT NULL DEFAULT '',
                location TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS products (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                farmer_id INTEGER NOT NULL REFERENCES users(id),
                name TEXT NOT NULL,
                category TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                quantity REAL NOT NULL CHECK(quantity > 0),
                unit TEXT NOT NULL,
                price REAL NOT NULL CHECK(price >= 0),
                location TEXT NOT NULL DEFAULT '',
                available INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                product_id INTEGER NOT NULL REFERENCES products(id),
                buyer_id INTEGER NOT NULL REFERENCES users(id),
                farmer_id INTEGER NOT NULL REFERENCES users(id),
                quantity REAL NOT NULL CHECK(quantity > 0),
                total REAL NOT NULL CHECK(total >= 0),
                status TEXT NOT NULL DEFAULT 'Pending',
                delivery_details TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
        """)


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
        con.execute(
            "INSERT INTO users(name,email,password_hash,role,business,location) VALUES(?,?,?,?,?,?)",
            (name.strip(), email.strip().lower(), password_digest(password), role, business.strip(), location.strip()),
        )


def login(email: str, password: str) -> dict | None:
    with connect() as con:
        row = con.execute("SELECT * FROM users WHERE email = ?", (email.strip().lower(),)).fetchone()
    if row and verify_password(password, row["password_hash"]):
        return dict(row)
    return None


def money(value: float) -> str:
    return f"₹{value:,.2f}"


def auth_screen() -> None:
    st.markdown("# 🌾 Farm2Biz")
    st.caption("A direct marketplace for farmers and business buyers")
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
                except sqlite3.IntegrityError:
                    st.error("An account with that email already exists.")


def add_product(user: dict) -> None:
    st.subheader("Add a product")
    with st.form("new_product", clear_on_submit=True):
        name = st.text_input("Product name")
        category = st.selectbox("Category", CATEGORIES)
        description = st.text_area("Description / quality notes")
        c1, c2, c3 = st.columns(3)
        quantity = c1.number_input("Available quantity", min_value=0.1, value=10.0, step=1.0)
        unit = c2.selectbox("Unit", UNITS)
        price = c3.number_input("Price per unit (₹)", min_value=0.0, value=0.0, step=1.0)
        location = st.text_input("Pickup location", value=user.get("location", ""))
        save = st.form_submit_button("Publish listing", type="primary")
    if save:
        if not name.strip() or price <= 0 or not location.strip():
            st.error("Enter a product name, a price above zero, and a pickup location.")
            return
        with connect() as con:
            con.execute("INSERT INTO products(farmer_id,name,category,description,quantity,unit,price,location) VALUES(?,?,?,?,?,?,?,?)",
                        (user["id"], name.strip(), category, description.strip(), quantity, unit, price, location.strip()))
        st.success("Your product is now listed.")
        st.rerun()


def marketplace(user: dict) -> None:
    st.subheader("Available produce")
    c1, c2, c3 = st.columns([2, 1, 1])
    query = c1.text_input("Search products or locations", placeholder="e.g. tomatoes, Nashik")
    category = c2.selectbox("Category", ["All categories", *CATEGORIES])
    sort = c3.selectbox("Sort by", ["Newest", "Price: low to high", "Price: high to low"])
    sql = "SELECT p.*,u.name AS farmer_name,u.location AS farmer_location FROM products p JOIN users u ON u.id=p.farmer_id WHERE p.available=1 AND p.quantity>0"
    args: list = []
    if query.strip():
        sql += " AND (p.name LIKE ? OR p.location LIKE ? OR u.name LIKE ?)"
        term = f"%{query.strip()}%"
        args.extend([term, term, term])
    if category != "All categories":
        sql += " AND p.category=?"
        args.append(category)
    sql += {"Newest": " ORDER BY p.created_at DESC", "Price: low to high": " ORDER BY p.price ASC", "Price: high to low": " ORDER BY p.price DESC"}[sort]
    with connect() as con:
        rows = con.execute(sql, args).fetchall()
    if not rows:
        st.info("No matching products yet. Try another search or check back soon.")
        return
    for product in rows:
        with st.container(border=True):
            left, right = st.columns([3, 1])
            left.markdown(f"### {product['name']}  ·  {product['category']}")
            left.write(product["description"] or "Fresh produce available for direct purchase.")
            left.caption(f"Farmer: {product['farmer_name']}  ·  Pickup: {product['location']}  ·  Listed: {product['created_at'][:10]}")
            right.metric("Price", f"{money(product['price'])} / {product['unit']}")
            right.write(f"Available: **{product['quantity']:g} {product['unit']}**")
            if user["role"] == "Buyer":
                with st.form(f"order_{product['id']}"):
                    qty = st.number_input("Order quantity", min_value=0.1, max_value=float(product["quantity"]), value=min(1.0, float(product["quantity"])), step=0.1, key=f"qty_{product['id']}")
                    delivery = st.text_input("Delivery / transportation request", key=f"delivery_{product['id']}")
                    place = st.form_submit_button("Place order")
                if place:
                    with connect() as con:
                        latest = con.execute("SELECT quantity,price,farmer_id FROM products WHERE id=? AND available=1", (product["id"],)).fetchone()
                        if not latest or qty > latest["quantity"]:
                            st.error("The available quantity changed. Refresh and try again.")
                        else:
                            con.execute("INSERT INTO orders(product_id,buyer_id,farmer_id,quantity,total,delivery_details) VALUES(?,?,?,?,?,?)",
                                        (product["id"], user["id"], latest["farmer_id"], qty, qty * latest["price"], delivery.strip()))
                            con.execute("UPDATE products SET quantity=quantity-? WHERE id=?", (qty, product["id"]))
                    st.success("Order sent to the farmer.")
                    st.rerun()
            elif user["id"] == product["farmer_id"]:
                st.caption("This is your listing. Manage it under My products.")


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
            a.write(f"{order['quantity']:g} {order['unit']} · {money(order['total'])} · {order['created_at'][:16]}")
            a.write(f"{'Buyer' if user['role']=='Farmer' else 'Farmer'}: {counterparty}")
            a.write(f"Delivery: {order['delivery_details'] or 'To be arranged'}")
            if user["role"] == "Farmer":
                with b.form(f"status_{order['id']}"):
                    new_status = st.selectbox("Status", STATUSES, index=STATUSES.index(order["status"]), key=f"status_pick_{order['id']}")
                    if st.form_submit_button("Update status") and new_status != order["status"]:
                        with connect() as con:
                            con.execute("UPDATE orders SET status=? WHERE id=? AND farmer_id=?", (new_status, order["id"], user["id"]))
                        st.rerun()
            else:
                b.metric("Status", order["status"])


def products_page(user: dict) -> None:
    st.subheader("My products")
    with connect() as con:
        products = con.execute("SELECT * FROM products WHERE farmer_id=? ORDER BY created_at DESC", (user["id"],)).fetchall()
    if not products:
        st.info("You have not listed any products yet.")
        return
    for p in products:
        with st.container(border=True):
            left, right = st.columns([3, 1])
            left.markdown(f"**{p['name']}** · {p['category']}")
            left.write(f"{p['quantity']:g} {p['unit']} available · {money(p['price'])}/{p['unit']} · {p['location']}")
            with right:
                active = st.toggle("Available", value=bool(p["available"]), key=f"active_{p['id']}")
                if active != bool(p["available"]):
                    with connect() as con:
                        con.execute("UPDATE products SET available=? WHERE id=? AND farmer_id=?", (int(active), p["id"], user["id"]))
                    st.rerun()


def main() -> None:
    initialize_db()
    if not current_user():
        auth_screen()
        return
    user = current_user()
    with st.sidebar:
        st.markdown("## 🌾 Farm2Biz")
        st.write(f"**{user['name']}**")
        st.caption(f"{user['role']} · {user['location']}")
        if st.button("Sign out", use_container_width=True):
            st.session_state.pop("user", None)
            st.rerun()
        st.divider()
        nav_options = ["Marketplace", "Orders"] if user["role"] == "Buyer" else ["Marketplace", "My products", "Orders"]
        page = st.radio("Navigate", nav_options, label_visibility="collapsed")
    st.title({"Marketplace": "Find fresh produce", "My products": "Manage your listings", "Orders": "Track your orders"}[page])
    st.caption("Trade directly with local farmers and business buyers.")
    if page == "Marketplace":
        if user["role"] == "Farmer":
            with st.expander("List a product", expanded=False):
                add_product(user)
        marketplace(user)
    elif page == "My products":
        products_page(user)
    else:
        order_page(user)


if __name__ == "__main__":
    main()
