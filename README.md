# Farm2Biz — Farm-to-Business Marketplace

A Python and Streamlit prototype that connects farmers directly with restaurants, retailers, wholesalers, and food processors. It supports account creation, product listings, searchable produce, orders, delivery notes, and order status updates.

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

The app opens in your browser. SQLite creates `farm2biz.db` in this folder the first time the app starts. Set `FARM2BIZ_DB` to use a different database path.

## Try the main workflow

1. Create a **Farmer** account and list a product, such as tomatoes, with quantity, unit, price, and pickup location.
2. Sign out and create a **Buyer** account.
3. Search/filter the marketplace and place an order with a delivery request.
4. Sign back in as the farmer and update the order status as it progresses.

## Features

- Farmer and buyer registration and sign-in
- Salted PBKDF2 password hashes
- Farmer product creation and listing availability controls
- Search by product, farmer, or pickup location; category and price sorting
- Buyer orders with stock checks and automatic inventory reduction
- Farmer order status management and delivery/transport notes
- SQLite persistence with foreign key constraints

## Project structure

```text
app.py           Streamlit app and SQLite data access
requirements.txt Python dependency
farm2biz.db      Created locally on first run (ignored by Git)
```

## Scope and limitations

This is a classroom prototype. It does not process payments, verify identities, arrange a carrier, send notifications, or provide production-grade account recovery and deployment security. Delivery details are free-text coordination notes. Use a trusted deployment environment and persistent storage before using real customer data.

## Submission

See `outputs/Farm2Biz_Submission_Document.md` for a project summary and a ready-to-fill section for repository and video links.
