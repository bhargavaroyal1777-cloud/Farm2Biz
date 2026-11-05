# Farm2Biz — Farm-to-Business Marketplace

A Python and Streamlit marketplace that connects farmers directly with restaurants, retailers, wholesalers, and food processors. It supports analytics, product photos and quality grades, advanced filters, orders, notifications, buyer wishlists, and observed price insights.

## Run locally

1. Install Python 3.10 or newer.
2. In this folder, create and activate a virtual environment:

   ```powershell
   py -m venv .venv
   .\.venv\Scripts\Activate.ps1
   ```

3. Install the dependency and start the app:

   ```powershell
   python -m pip install -r requirements.txt
   streamlit run app.py
   ```

The app opens in your browser. SQLite creates `farm2biz.db` in this folder the first time the app starts. Existing SQLite data is migrated additively; accounts, products, and orders are preserved. Set `FARM2BIZ_DB` to move the database to another durable local path.

## Try the main workflow

1. Create a **Farmer** account and list a product, such as tomatoes, with quantity, unit, price, and pickup location.
2. Sign out and create a **Buyer** account.
3. Search/filter the marketplace and place an order with a delivery request.
4. Sign back in as the farmer and update the order status as it progresses.

## Features

- Farmer and buyer registration and sign-in
- Salted PBKDF2 password hashes
- Marketplace-wide and role-specific analytics dashboards
- Product photo upload, Grade A/B/C descriptions, and listing availability controls
- Search plus location, price, category, and quality-grade filters
- Buyer ordering with atomic inventory reservation and stock restoration after rejection/cancellation
- Farmer order management, delivery notes, buyer wishlist, and in-app order notifications
- Current listing price comparison and real observed price history (no generated sample data)
- SQLite WAL, full synchronous writes, startup integrity checks, and additive schema migrations
- Optional PostgreSQL backend using `DATABASE_URL` for durable Streamlit Community Cloud storage

## Project structure

```text
app.py           Streamlit UI, marketplace operations, and data access
requirements.txt App dependencies
farm2biz.db      Local SQLite database (created on first run, ignored by Git)
.streamlit/      Green-and-white Streamlit theme configuration
tests/           Automated database and transaction checks
```

## Scope and limitations

This is a classroom prototype. It does not process payments, verify identities, arrange a carrier, or provide production-grade account recovery. Delivery details are free-text coordination notes. Product photos are stored in the configured database.

### Persistent storage on Streamlit Community Cloud

Community Cloud does not guarantee that local files such as SQLite databases survive restarts or redeployment. For durable hosted accounts, orders, images, notifications, and price history, provision a PostgreSQL database and add this value in the app's Streamlit Cloud **Settings → Secrets** (never commit credentials):

```toml
DATABASE_URL = "postgresql://USER:PASSWORD@HOST:5432/DATABASE?sslmode=require"
```

The application selects PostgreSQL when `DATABASE_URL` is configured and otherwise uses SQLite. Existing local SQLite data is not copied automatically into PostgreSQL; export/import or a one-time migration is needed if existing local accounts/orders must appear in the hosted database. Cloud SQLite is suitable for a temporary classroom demo only.

## Submission

See `outputs/Farm2Biz_Submission_Document.md` for the submission details and links.
