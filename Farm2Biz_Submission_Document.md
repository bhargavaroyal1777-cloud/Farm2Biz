# Farm2Biz — Project Submission

**Subject:** Python Programming  
**Sector:** Agriculture  
**Project type:** Web-based farm-to-business marketplace

## 1. Project overview

Farm2Biz is a marketplace prototype that helps small farmers list agricultural products and connect directly with business buyers such as restaurants, retailers, wholesalers, and food-processing companies. Farmers publish products, quantities, prices, and pickup locations. Buyers search listings and place orders, including delivery or transportation requests. Farmers can review orders and update their status.

## 2. Problem statement

Small farmers may depend on intermediaries to find buyers. This can limit direct access to customers and make it harder to communicate prices, available quantities, and delivery needs. Business buyers also need a convenient way to discover local produce and coordinate purchases.

## 3. Proposed solution

Farm2Biz provides one web application for farmers and buyers. Farmer accounts manage produce listings and incoming orders. Buyer accounts search and filter available products and submit orders. The application records order quantities, totals, delivery notes, and progress status in a local SQLite database.

## 4. Objectives

- Provide separate farmer and buyer accounts.
- Let farmers publish and manage agricultural product listings.
- Help buyers discover products by keyword and category and sort by price.
- Record orders and reduce listed inventory when orders are placed.
- Make order status and transportation requests visible to both sides.

## 5. Main features

1. Farmer and buyer registration and sign-in.
2. Product listings with category, description, quantity, unit, price, and pickup location.
3. Marketplace search, category filters, and price sorting.
4. Buyer order placement with an optional delivery request.
5. Farmer order status updates: Pending, Accepted, Ready for pickup, In transit, Completed, and Cancelled.
6. Farmer controls to pause or resume a product listing.

## 6. Technologies used

- **Python:** application logic and database operations.
- **Streamlit:** interactive web interface.
- **SQLite:** persistent local storage for accounts, products, and orders.
- **Git/GitHub:** source control and repository hosting.

## 7. How to run

From the project folder, install dependencies and launch the Streamlit app:

```bash
python -m pip install -r requirements.txt
streamlit run app.py
```

The database is initialized automatically on first launch. Detailed setup and a sample workflow are in `README.md`.

## 8. Expected outcome

The application demonstrates a direct digital channel for farmers and business buyers to share produce availability, submit orders, and coordinate delivery details. It is intended as a functional educational prototype for more transparent agricultural trading.

## 9. Demo video plan (maximum 5 minutes)

- **0:00–0:30:** Introduce the problem and Farm2Biz.
- **0:30–1:15:** Register/sign in as a farmer and publish a product.
- **1:15–2:15:** Sign in as a buyer, search/filter, and place an order.
- **2:15–3:15:** Return to the farmer account and update order status; show delivery notes.
- **3:15–4:00:** Show the SQLite-backed listings and summarize the technologies and expected benefits.

## 10. Submission links

- **GitHub repository:** https://github.com/bhargavaroyal1777-cloud/Farm2Biz
- **YouTube demo (up to 5 minutes):** [Add video URL]

## 11. Future improvements

Potential extensions include verified profiles, image uploads, in-app messaging, payment integration, carrier coordination, delivery tracking, notifications, and deployment with managed persistent storage.
