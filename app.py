
import sqlite3
from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st

DB_FILE = Path(__file__).with_name("canteen.db")

st.set_page_config(
    page_title="Canteen Order Management",
    page_icon="🍽️",
    layout="wide"
)


# ---------------- DATABASE ----------------

def get_connection():
    return sqlite3.connect(DB_FILE)


def init_db():
    with get_connection() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS menu (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                category TEXT NOT NULL,
                price REAL NOT NULL,
                available INTEGER NOT NULL DEFAULT 1
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                customer_name TEXT NOT NULL,
                total REAL NOT NULL,
                status TEXT NOT NULL DEFAULT 'Placed',
                created_at TEXT NOT NULL
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS order_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                order_id INTEGER NOT NULL,
                item_name TEXT NOT NULL,
                price REAL NOT NULL,
                quantity INTEGER NOT NULL,
                subtotal REAL NOT NULL
            )
        """)

        existing = conn.execute(
            "SELECT COUNT(*) FROM menu"
        ).fetchone()[0]

        if existing == 0:
            foods = [
                ("Veg Idli", "Breakfast", 30),
                ("Masala Dosa", "Breakfast", 50),
                ("Poori", "Breakfast", 40),
                ("Veg Meals", "Lunch", 90),
                ("Chicken Biryani", "Lunch", 140),
                ("Curd Rice", "Lunch", 50),
                ("Veg Fried Rice", "Snacks", 80),
                ("Samosa", "Snacks", 20),
                ("Tea", "Drinks", 15),
                ("Coffee", "Drinks", 20),
            ]
            conn.executemany(
                "INSERT OR IGNORE INTO menu "
                "(name, category, price) VALUES (?, ?, ?)",
                foods
            )


init_db()


def read_menu(available_only=False):
    query = "SELECT * FROM menu"
    if available_only:
        query += " WHERE available = 1"
    query += " ORDER BY category, name"

    with get_connection() as conn:
        return pd.read_sql_query(query, conn)


def save_order(customer_name, cart):
    total = sum(
        item["price"] * item["quantity"]
        for item in cart.values()
    )

    with get_connection() as conn:
        cursor = conn.execute(
            """INSERT INTO orders
            (customer_name, total, status, created_at)
            VALUES (?, ?, 'Placed', ?)""",
            (
                customer_name.strip(),
                total,
                datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            )
        )

        order_id = cursor.lastrowid

        for item in cart.values():
            subtotal = item["price"] * item["quantity"]
            conn.execute(
                """INSERT INTO order_items
                (order_id, item_name, price, quantity, subtotal)
                VALUES (?, ?, ?, ?, ?)""",
                (
                    order_id,
                    item["name"],
                    item["price"],
                    item["quantity"],
                    subtotal
                )
            )

    return order_id, total


def get_orders():
    with get_connection() as conn:
        return pd.read_sql_query(
            "SELECT * FROM orders ORDER BY id DESC",
            conn
        )


def get_order_items(order_id):
    with get_connection() as conn:
        return pd.read_sql_query(
            "SELECT item_name AS Item, price AS Price, "
            "quantity AS Quantity, subtotal AS Subtotal "
            "FROM order_items WHERE order_id = ?",
            conn,
            params=(int(order_id),)
        )


# ---------------- SIDEBAR ----------------

st.sidebar.title("🍽️ Campus Canteen")
st.sidebar.caption("Order Management System")

page = st.sidebar.radio(
    "Navigation",
    [
        "Dashboard",
        "Place Order",
        "Menu Management",
        "Order History",
        "Sales Report"
    ]
)


# ---------------- DASHBOARD ----------------

if page == "Dashboard":
    st.title("🍽️ Canteen Dashboard")
    st.write("Welcome to the Canteen Order Management System!")

    orders = get_orders()
    menu = read_menu()

    total_orders = len(orders)
    revenue = (
        orders.loc[orders["status"] != "Cancelled", "total"].sum()
        if not orders.empty else 0
    )
    available_items = (
        int((menu["available"] == 1).sum())
        if not menu.empty else 0
    )

    a, b, c = st.columns(3)
    a.metric("Total Orders", total_orders)
    b.metric("Recorded Sales", f"₹{revenue:.2f}")
    c.metric("Available Food Items", available_items)

    st.subheader("Available Menu")
    st.dataframe(
        menu[menu["available"] == 1][
            ["name", "category", "price"]
        ].rename(columns={
            "name": "Food Item",
            "category": "Category",
            "price": "Price (₹)"
        }),
        use_container_width=True,
        hide_index=True
    )


# ---------------- PLACE ORDER ----------------

elif page == "Place Order":
    st.title("🛒 Place a New Order")

    menu = read_menu(available_only=True)

    if menu.empty:
        st.warning("No food items are available.")
    else:
        if "cart" not in st.session_state:
            st.session_state.cart = {}

        if "last_bill" not in st.session_state:
            st.session_state.last_bill = None

        customer_name = st.text_input("Customer Name")

        categories = ["All"] + sorted(
            menu["category"].unique().tolist()
        )
        category = st.selectbox("Food Category", categories)

        filtered = menu.copy()
        if category != "All":
            filtered = filtered[filtered["category"] == category]

        if not filtered.empty:
            with st.form("add_item_form"):
                item_name = st.selectbox(
                    "Choose Food Item", filtered["name"].tolist()
                )
                row = filtered[filtered["name"] == item_name].iloc[0]
                st.write(f"Price: ₹{row['price']:.2f}")

                quantity = st.number_input(
                    "Quantity", min_value=1, max_value=100,
                    value=1, step=1
                )
                add = st.form_submit_button("Add to Cart")

            if add:
                name = row["name"]
                price = float(row["price"])

                if name in st.session_state.cart:
                    st.session_state.cart[name]["quantity"] += int(quantity)
                else:
                    st.session_state.cart[name] = {
                        "name": name,
                        "price": price,
                        "quantity": int(quantity)
                    }

                st.session_state.last_bill = None
                st.rerun()

        st.subheader("Your Cart")
        cart = st.session_state.cart

        if cart:
            cart_rows = [
                {
                    "Item": item["name"],
                    "Price (₹)": item["price"],
                    "Quantity": item["quantity"],
                    "Subtotal (₹)": item["price"] * item["quantity"]
                }
                for item in cart.values()
            ]

            st.dataframe(
                pd.DataFrame(cart_rows),
                use_container_width=True,
                hide_index=True
            )

            total = sum(
                item["price"] * item["quantity"]
                for item in cart.values()
            )
            st.subheader(f"Total Bill: ₹{total:.2f}")

            col1, col2 = st.columns(2)

            with col1:
                if st.button("Clear Cart"):
                    st.session_state.cart = {}
                    st.session_state.last_bill = None
                    st.rerun()

            with col2:
                if st.button("Place Order", type="primary"):
                    if not customer_name.strip():
                        st.warning("Please enter the customer name.")
                    elif not cart:
                        st.warning("Please add food items.")
                    else:
                        order_id, total = save_order(
                            customer_name, cart
                        )

                        bill_lines = [
                            "CANTEEN ORDER RECEIPT",
                            "==============================",
                            f"Order ID: {order_id}",
                            f"Customer: {customer_name.strip()}",
                            f"Date: {datetime.now():%d-%m-%Y %H:%M}",
                            "------------------------------",
                            "ITEM | QTY | PRICE | SUBTOTAL",
                            "------------------------------"
                        ]

                        for item in cart.values():
                            subtotal = item["price"] * item["quantity"]
                            bill_lines.append(
                                f"{item['name']} | {item['quantity']} | "
                                f"Rs. {item['price']:.2f} | "
                                f"Rs. {subtotal:.2f}"
                            )

                        bill_lines.extend([
                            "------------------------------",
                            f"TOTAL: Rs. {total:.2f}",
                            "Thank you for visiting!"
                        ])

                        st.session_state.last_bill = {
                            "order_id": order_id,
                            "text": "\n".join(bill_lines)
                        }
                        st.session_state.cart = {}
                        st.rerun()

        else:
            st.info("Your cart is empty. Add food items to continue.")

        if st.session_state.last_bill:
            bill = st.session_state.last_bill
            st.success(
                f"Order #{bill['order_id']} placed successfully!"
            )
            st.text_area(
                "Bill Receipt", bill["text"], height=250
            )
            st.download_button(
                "Download Bill",
                data=bill["text"],
                file_name=f"canteen_bill_{bill['order_id']}.txt",
                mime="text/plain",
                key=f"download_bill_{bill['order_id']}"
            )


# ---------------- MENU MANAGEMENT ----------------

elif page == "Menu Management":
    st.title("📋 Menu Management")

    st.subheader("Current Menu")
    menu = read_menu()

    st.dataframe(
        menu[["id", "name", "category", "price", "available"]],
        use_container_width=True,
        hide_index=True
    )

    st.subheader("Add New Food Item")
    with st.form("new_food_form"):
        name = st.text_input("Food Name")
        category = st.selectbox(
            "Category",
            ["Breakfast", "Lunch", "Snacks", "Drinks", "Other"]
        )
        price = st.number_input(
            "Price (₹)", min_value=1.0, value=30.0, step=5.0
        )
        submitted = st.form_submit_button("Add Food Item")

    if submitted:
        if not name.strip():
            st.warning("Please enter a food name.")
        else:
            try:
                with get_connection() as conn:
                    conn.execute(
                        "INSERT INTO menu (name, category, price, available) "
                        "VALUES (?, ?, ?, 1)",
                        (name.strip(), category, float(price))
                    )
                st.success(f"{name.strip()} added successfully!")
                st.rerun()
            except sqlite3.IntegrityError:
                st.error("This food item already exists.")

    st.subheader("Update Food Availability")
    menu = read_menu()

    if not menu.empty:
        selected_id = st.selectbox(
            "Select Food Item",
            menu["id"].tolist(),
            format_func=lambda x: menu.loc[
                menu["id"] == x, "name"
            ].iloc[0]
        )
        current = menu.loc[
            menu["id"] == selected_id, "available"
        ].iloc[0]

        available = st.checkbox(
            "Item is available", value=bool(current)
        )

        if st.button("Update Availability"):
            with get_connection() as conn:
                conn.execute(
                    "UPDATE menu SET available = ? WHERE id = ?",
                    (int(available), int(selected_id))
                )
            st.success("Availability updated!")
            st.rerun()


# ---------------- ORDER HISTORY ----------------

elif page == "Order History":
    st.title("📜 Order History")

    orders = get_orders()

    if orders.empty:
        st.info("No orders have been placed yet.")
    else:
        st.dataframe(
            orders,
            use_container_width=True,
            hide_index=True
        )

        order_id = st.selectbox(
            "Select Order ID", orders["id"].tolist()
        )

        st.subheader(f"Items in Order #{order_id}")
        st.dataframe(
            get_order_items(order_id),
            use_container_width=True,
            hide_index=True
        )

        current_status = orders.loc[
            orders["id"] == order_id, "status"
        ].iloc[0]

        statuses = ["Placed", "Preparing", "Ready", "Completed", "Cancelled"]
        selected_status = st.selectbox(
            "Update Order Status",
            statuses,
            index=statuses.index(current_status)
            if current_status in statuses else 0
        )

        if st.button("Save Order Status"):
            with get_connection() as conn:
                conn.execute(
                    "UPDATE orders SET status = ? WHERE id = ?",
                    (selected_status, int(order_id))
                )
            st.success("Order status updated!")
            st.rerun()


# ---------------- SALES REPORT ----------------

elif page == "Sales Report":
    st.title("📊 Sales Report")

    orders = get_orders()

    if orders.empty:
        st.info("No sales data available yet.")
    else:
        valid = orders[orders["status"] != "Cancelled"].copy()
        total_sales = valid["total"].sum()
        count = len(valid)
        average = total_sales / count if count else 0

        a, b, c = st.columns(3)
        a.metric("Net Recorded Sales", f"₹{total_sales:.2f}")
        b.metric("Non-cancelled Orders", count)
        c.metric("Average Order Value", f"₹{average:.2f}")

        if not valid.empty:
            valid["Date"] = pd.to_datetime(
                valid["created_at"]
            ).dt.date

            daily = valid.groupby("Date")["total"].sum()
            st.subheader("Sales by Date")
            st.line_chart(daily)

            with get_connection() as conn:
                popular = pd.read_sql_query(
                    """SELECT item_name AS Item,
                    SUM(quantity) AS Quantity Sold,
                    SUM(subtotal) AS Sales
                    FROM order_items
                    JOIN orders ON orders.id = order_items.order_id
                    WHERE orders.status != 'Cancelled'
                    GROUP BY item_name
                    ORDER BY Quantity Sold DESC""",
                    conn
                )

            st.subheader("Popular Food Items")
            st.dataframe(
                popular,
                use_container_width=True,
                hide_index=True
            )

st.sidebar.divider()
st.sidebar.caption("Canteen Management System • Python + Streamlit")
