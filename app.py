from flask import Flask, render_template, request, redirect, url_for, flash
import sqlite3
from pathlib import Path

app = Flask(__name__)
app.secret_key = "inventory-project-key"

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "inventory.db"


# ---------------- DATABASE CONNECTION ----------------

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


# ---------------- DATABASE INITIALIZATION ----------------

def initialize_database():
    with get_db() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS suppliers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                phone TEXT,
                email TEXT,
                address TEXT
            );

            CREATE TABLE IF NOT EXISTS products (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                price REAL NOT NULL CHECK(price >= 0),
                quantity INTEGER NOT NULL CHECK(quantity >= 0),
                category TEXT NOT NULL,
                supplier_id INTEGER,
                FOREIGN KEY (supplier_id)
                    REFERENCES suppliers(id)
                    ON DELETE SET NULL
            );

            CREATE TABLE IF NOT EXISTS sales (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                customer_name TEXT NOT NULL,
                sale_date TEXT NOT NULL DEFAULT
                    (datetime('now', 'localtime')),
                total REAL NOT NULL CHECK(total >= 0)
            );

            CREATE TABLE IF NOT EXISTS sale_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sale_id INTEGER NOT NULL,
                product_id INTEGER,
                product_name TEXT NOT NULL,
                quantity INTEGER NOT NULL CHECK(quantity > 0),
                unit_price REAL NOT NULL CHECK(unit_price >= 0),
                FOREIGN KEY (sale_id) REFERENCES sales(id),
                FOREIGN KEY (product_id)
                    REFERENCES products(id)
                    ON DELETE SET NULL
            );
        """)


# ---------------- DASHBOARD ----------------

@app.route("/")
def dashboard():
    with get_db() as conn:
        stats = {
            "products": conn.execute(
                "SELECT COUNT(*) FROM products"
            ).fetchone()[0],

            "suppliers": conn.execute(
                "SELECT COUNT(*) FROM suppliers"
            ).fetchone()[0],

            "units": conn.execute(
                "SELECT COALESCE(SUM(quantity), 0) FROM products"
            ).fetchone()[0],

            "revenue": conn.execute(
                "SELECT COALESCE(SUM(total), 0) FROM sales"
            ).fetchone()[0]
        }

        low_stock = conn.execute("""
            SELECT name, quantity, category
            FROM products
            WHERE quantity <= 5
            ORDER BY quantity ASC
        """).fetchall()

        recent_sales = conn.execute("""
            SELECT id, customer_name, sale_date, total
            FROM sales
            ORDER BY id DESC
            LIMIT 5
        """).fetchall()

    return render_template(
        "dashboard.html",
        stats=stats,
        low_stock=low_stock,
        recent_sales=recent_sales
    )


# ---------------- PRODUCT MANAGEMENT ----------------

@app.route("/products", methods=["GET", "POST"])
def products():
    with get_db() as conn:

        # Add a product
        if request.method == "POST":
            name = request.form.get("name", "").strip()
            category = request.form.get("category", "").strip()
            supplier_id = request.form.get("supplier_id") or None

            try:
                price = float(request.form.get("price", ""))
                quantity = int(request.form.get("quantity", ""))

                if (
                    not name
                    or not category
                    or price < 0
                    or quantity < 0
                ):
                    raise ValueError

            except ValueError:
                flash("Enter valid product details.", "error")
                return redirect(url_for("products"))

            try:
                conn.execute("""
                    INSERT INTO products
                        (name, price, quantity, category, supplier_id)
                    VALUES (?, ?, ?, ?, ?)
                """, (
                    name, price, quantity, category, supplier_id
                ))

                flash("Product added successfully.", "success")

            except sqlite3.Error:
                flash("Unable to add product. Check supplier details.",
                      "error")

            return redirect(url_for("products"))

        # Search and display products
        search = request.args.get("search", "").strip()

        items = conn.execute("""
            SELECT p.*, s.name AS supplier_name
            FROM products p
            LEFT JOIN suppliers s ON p.supplier_id = s.id
            WHERE p.name LIKE ? OR p.category LIKE ?
            ORDER BY p.id DESC
        """, (
            f"%{search}%", f"%{search}%"
        )).fetchall()

        supplier_list = conn.execute("""
            SELECT id, name
            FROM suppliers
            ORDER BY name
        """).fetchall()

    return render_template(
        "products.html",
        products=items,
        suppliers=supplier_list,
        search=search
    )


# Edit or update a product
@app.route("/products/edit/<int:product_id>", methods=["GET", "POST"])
def edit_product(product_id):
    with get_db() as conn:

        product = conn.execute("""
            SELECT *
            FROM products
            WHERE id = ?
        """, (product_id,)).fetchone()

        if product is None:
            flash("Product not found.", "error")
            return redirect(url_for("products"))

        if request.method == "POST":
            name = request.form.get("name", "").strip()
            category = request.form.get("category", "").strip()
            supplier_id = request.form.get("supplier_id") or None

            try:
                price = float(request.form.get("price", ""))
                quantity = int(request.form.get("quantity", ""))

                if (
                    not name
                    or not category
                    or price < 0
                    or quantity < 0
                ):
                    raise ValueError

                conn.execute("""
                    UPDATE products
                    SET name = ?,
                        category = ?,
                        price = ?,
                        quantity = ?,
                        supplier_id = ?
                    WHERE id = ?
                """, (
                    name, category, price,
                    quantity, supplier_id, product_id
                ))

                flash("Product updated successfully.", "success")
                return redirect(url_for("products"))

            except ValueError:
                flash("Enter valid product details.", "error")

            except sqlite3.Error:
                flash("Unable to update product. Check supplier details.",
                      "error")

        supplier_list = conn.execute("""
            SELECT id, name
            FROM suppliers
            ORDER BY name
        """).fetchall()

    return render_template(
        "edit_product.html",
        product=product,
        suppliers=supplier_list
    )


# Delete a product
@app.route("/products/delete/<int:product_id>", methods=["POST"])
def delete_product(product_id):
    with get_db() as conn:
        conn.execute("""
            DELETE FROM products
            WHERE id = ?
        """, (product_id,))

    flash("Product deleted successfully.", "success")
    return redirect(url_for("products"))


# ---------------- SUPPLIER MANAGEMENT ----------------

@app.route("/suppliers", methods=["GET", "POST"])
def suppliers():
    with get_db() as conn:

        # Add a supplier
        if request.method == "POST":
            name = request.form.get("name", "").strip()
            phone = request.form.get("phone", "").strip()
            email = request.form.get("email", "").strip()
            address = request.form.get("address", "").strip()

            if not name:
                flash("Supplier name is required.", "error")
                return redirect(url_for("suppliers"))

            conn.execute("""
                INSERT INTO suppliers (name, phone, email, address)
                VALUES (?, ?, ?, ?)
            """, (name, phone, email, address))

            flash("Supplier added successfully.", "success")
            return redirect(url_for("suppliers"))

        # Display suppliers and linked product counts
        supplier_list = conn.execute("""
            SELECT s.*, COUNT(p.id) AS product_count
            FROM suppliers s
            LEFT JOIN products p ON p.supplier_id = s.id
            GROUP BY s.id
            ORDER BY s.id DESC
        """).fetchall()

    return render_template(
        "suppliers.html",
        suppliers=supplier_list
    )


# Delete a supplier
@app.route("/suppliers/delete/<int:supplier_id>", methods=["POST"])
def delete_supplier(supplier_id):
    with get_db() as conn:
        conn.execute("""
            DELETE FROM suppliers
            WHERE id = ?
        """, (supplier_id,))

    flash("Supplier deleted. Linked products are retained.", "success")
    return redirect(url_for("suppliers"))


# ---------------- SALES AND ORDER TRACKING ----------------

@app.route("/sales", methods=["GET", "POST"])
def sales():
    with get_db() as conn:

        if request.method == "POST":
            customer = request.form.get(
                "customer_name", ""
            ).strip()

            try:
                product_id = int(request.form.get("product_id", ""))
                quantity = int(request.form.get("quantity", ""))

                if not customer or quantity <= 0:
                    raise ValueError

            except ValueError:
                flash("Enter a customer name and valid quantity.", "error")
                return redirect(url_for("sales"))

            try:
                # Start a transaction before checking stock.
                conn.execute("BEGIN IMMEDIATE")

                product = conn.execute("""
                    SELECT id, name, price, quantity
                    FROM products
                    WHERE id = ?
                """, (product_id,)).fetchone()

                if product is None:
                    raise ValueError("Product not found.")

                if product["quantity"] < quantity:
                    raise ValueError("Not enough stock available.")

                total = round(product["price"] * quantity, 2)

                cursor = conn.execute("""
                    INSERT INTO sales (customer_name, total)
                    VALUES (?, ?)
                """, (customer, total))

                sale_id = cursor.lastrowid

                conn.execute("""
                    INSERT INTO sale_items
                        (sale_id, product_id, product_name,
                         quantity, unit_price)
                    VALUES (?, ?, ?, ?, ?)
                """, (
                    sale_id,
                    product["id"],
                    product["name"],
                    quantity,
                    product["price"]
                ))

                # Reduce stock only if enough units remain.
                update = conn.execute("""
                    UPDATE products
                    SET quantity = quantity - ?
                    WHERE id = ? AND quantity >= ?
                """, (quantity, product_id, quantity))

                if update.rowcount != 1:
                    raise ValueError("Unable to update stock.")

                conn.commit()

                flash(
                    f"Sale recorded successfully. Total: Rs. {total:.2f}",
                    "success"
                )

            except (ValueError, sqlite3.Error) as error:
                conn.rollback()
                flash(str(error) or "Unable to record sale.", "error")

            return redirect(url_for("sales"))

        # Products currently available for sale
        product_list = conn.execute("""
            SELECT id, name, price, quantity
            FROM products
            WHERE quantity > 0
            ORDER BY name
        """).fetchall()

        # Previous sales and their items
        sale_list = conn.execute("""
            SELECT s.*,
                   GROUP_CONCAT(
                       si.product_name || ' x' || si.quantity, ', '
                   ) AS items
            FROM sales s
            LEFT JOIN sale_items si ON si.sale_id = s.id
            GROUP BY s.id
            ORDER BY s.id DESC
        """).fetchall()

    return render_template(
        "sales.html",
        products=product_list,
        sales=sale_list
    )


# ---------------- SQL ANALYTICS AND REPORTS ----------------

@app.route("/reports")
def reports():
    with get_db() as conn:

        # Total revenue
        revenue = conn.execute("""
            SELECT COALESCE(SUM(total), 0)
            FROM sales
        """).fetchone()[0]

        # Best-selling products
        best_sellers = conn.execute("""
            SELECT product_name,
                   SUM(quantity) AS units_sold,
                   SUM(quantity * unit_price) AS sales_amount
            FROM sale_items
            GROUP BY product_name
            ORDER BY units_sold DESC
            LIMIT 10
        """).fetchall()

        # Low-stock products
        low_stock = conn.execute("""
            SELECT name, category, quantity
            FROM products
            WHERE quantity <= 5
            ORDER BY quantity ASC
        """).fetchall()

        # Inventory totals by category
        category_stock = conn.execute("""
            SELECT category,
                   COUNT(*) AS product_count,
                   SUM(quantity) AS units
            FROM products
            GROUP BY category
            ORDER BY category
        """).fetchall()

    return render_template(
        "reports.html",
        revenue=revenue,
        best_sellers=best_sellers,
        low_stock=low_stock,
        category_stock=category_stock
    )


# ---------------- START APPLICATION ----------------

if __name__ == "__main__":
    initialize_database()
    app.run(debug=True)