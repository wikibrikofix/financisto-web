"""Financisto Web - Flask backend API with full CRUD."""
import os
import time
from flask import Flask, jsonify, request
from flask_cors import CORS
import psycopg2
import psycopg2.extras
from import_backup import parse_backup, import_to_db

app = Flask(__name__)
CORS(app)

DB_URL = os.environ.get("DATABASE_URL", "postgresql://financisto:financisto@db:5432/financisto")


def get_db():
    conn = psycopg2.connect(DB_URL)
    conn.autocommit = True
    return conn


def now_ms():
    return int(time.time() * 1000)


def next_id(cur, table):
    cur.execute(f'SELECT COALESCE(MAX(id), 0) + 1 as next_id FROM "{table}"')
    return cur.fetchone()["next_id"]


# --- Health ---
@app.route("/api/health")
def health():
    return jsonify({"status": "ok"})


# --- Import ---
@app.route("/api/import", methods=["POST"])
def import_backup_endpoint():
    if "file" not in request.files:
        return jsonify({"error": "No file provided"}), 400
    content = request.files["file"].read()
    try:
        records = parse_backup(content)
        import_to_db(records, DB_URL)
        summary = {t: len([r for r in rows if r]) for t, rows in records.items()}
        return jsonify({"status": "ok", "imported": summary})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# --- Currencies ---
@app.route("/api/currencies")
def list_currencies():
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SELECT * FROM currency WHERE is_active = TRUE ORDER BY name")
    rows = cur.fetchall()
    cur.close(); conn.close()
    return jsonify(rows)


# --- Accounts ---
@app.route("/api/accounts")
def list_accounts():
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("""
        SELECT a.*, c.symbol as currency_symbol, c.name as currency_name, c.decimals as currency_decimals
        FROM account a JOIN currency c ON a.currency_id = c.id
        ORDER BY a.sort_order, a.title
    """)
    rows = cur.fetchall()
    cur.close(); conn.close()
    return jsonify(rows)


@app.route("/api/accounts", methods=["POST"])
def create_account():
    d = request.json
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    new_id = next_id(cur, "account")
    cur.execute("""
        INSERT INTO account (id, title, creation_date, currency_id, type, issuer, number,
            is_active, is_include_into_totals, total_limit, card_issuer, closing_day, payment_day, note, sort_order)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *
    """, (new_id, d["title"], now_ms(), d["currency_id"], d.get("type", "CASH"),
          d.get("issuer"), d.get("number"), d.get("is_active", True),
          d.get("is_include_into_totals", True), d.get("total_limit", 0),
          d.get("card_issuer"), d.get("closing_day", 0), d.get("payment_day", 0),
          d.get("note"), d.get("sort_order", 0)))
    row = cur.fetchone()
    cur.close(); conn.close()
    return jsonify(row), 201


@app.route("/api/accounts/<int:aid>", methods=["PUT"])
def update_account(aid):
    d = request.json
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("""
        UPDATE account SET title=%s, currency_id=%s, type=%s, issuer=%s, number=%s,
            is_active=%s, is_include_into_totals=%s, total_limit=%s, card_issuer=%s,
            closing_day=%s, payment_day=%s, note=%s, sort_order=%s
        WHERE id=%s RETURNING *
    """, (d["title"], d["currency_id"], d.get("type", "CASH"), d.get("issuer"),
          d.get("number"), d.get("is_active", True), d.get("is_include_into_totals", True),
          d.get("total_limit", 0), d.get("card_issuer"), d.get("closing_day", 0),
          d.get("payment_day", 0), d.get("note"), d.get("sort_order", 0), aid))
    row = cur.fetchone()
    cur.close(); conn.close()
    if not row:
        return jsonify({"error": "not found"}), 404
    return jsonify(row)


@app.route("/api/accounts/<int:aid>", methods=["DELETE"])
def delete_account(aid):
    conn = get_db()
    cur = conn.cursor()
    # Soft delete: mark inactive
    cur.execute("UPDATE account SET is_active = FALSE WHERE id = %s", (aid,))
    cur.close(); conn.close()
    return jsonify({"status": "ok"})


def update_account_balance(cur, account_id, delta):
    """Incrementally update account balance by delta."""
    cur.execute("UPDATE account SET total_amount = total_amount + %s WHERE id = %s", (delta, account_id))


# --- Transactions ---
@app.route("/api/accounts/<int:aid>/transactions")
def account_transactions(aid):
    limit = request.args.get("limit", 50, type=int)
    offset = request.args.get("offset", 0, type=int)
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("""
        SELECT t.*, cat.title as category_title, p.title as payee_title,
               proj.title as project_title
        FROM "transaction" t
        LEFT JOIN category cat ON t.category_id = cat.id
        LEFT JOIN payee p ON t.payee_id = p.id
        LEFT JOIN project proj ON t.project_id = proj.id
        WHERE t.from_account_id = %s AND t.parent_id = 0 AND t.is_template = 0
        ORDER BY t.datetime DESC
        LIMIT %s OFFSET %s
    """, (aid, limit, offset))
    rows = cur.fetchall()
    cur.close(); conn.close()
    return jsonify(rows)


@app.route("/api/transactions")
def list_transactions():
    limit = request.args.get("limit", 50, type=int)
    offset = request.args.get("offset", 0, type=int)
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("""
        SELECT t.*, cat.title as category_title, p.title as payee_title,
               a.title as account_title, cur.symbol as currency_symbol, cur.decimals as currency_decimals
        FROM "transaction" t
        LEFT JOIN category cat ON t.category_id = cat.id
        LEFT JOIN payee p ON t.payee_id = p.id
        LEFT JOIN account a ON t.from_account_id = a.id
        LEFT JOIN currency cur ON a.currency_id = cur.id
        WHERE t.parent_id = 0 AND t.is_template = 0
        ORDER BY t.datetime DESC
        LIMIT %s OFFSET %s
    """, (limit, offset))
    rows = cur.fetchall()
    cur.close(); conn.close()
    return jsonify(rows)


@app.route("/api/transactions", methods=["POST"])
def create_transaction():
    d = request.json
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    new_id = next_id(cur, "transaction")
    dt = d.get("datetime", now_ms())
    cur.execute("""
        INSERT INTO "transaction" (id, from_account_id, to_account_id, category_id,
            project_id, payee_id, note, from_amount, to_amount, datetime, status, parent_id, is_template)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,0,0) RETURNING *
    """, (new_id, d["from_account_id"], d.get("to_account_id", 0),
          d.get("category_id", 0), d.get("project_id", 0), d.get("payee_id", 0),
          d.get("note"), d["from_amount"], abs(d.get("to_amount", 0)) if d.get("to_account_id") else d.get("to_amount", 0), dt,
          d.get("status", "UR")))
    row = cur.fetchone()
    # Update account balance incrementally
    update_account_balance(cur, d["from_account_id"], d["from_amount"])
    if d.get("to_account_id"):
        to_amt = d.get("to_amount", 0)
        if to_amt == 0:
            to_amt = abs(d["from_amount"])
        elif to_amt < 0:
            to_amt = abs(to_amt)
        update_account_balance(cur, d["to_account_id"], to_amt)
    # Update last_transaction_date
    cur.execute("UPDATE account SET last_transaction_date = %s WHERE id = %s", (dt, d["from_account_id"]))
    cur.close(); conn.close()
    return jsonify(row), 201


@app.route("/api/transactions/<int:tid>", methods=["PUT"])
def update_transaction(tid):
    d = request.json
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    # Get old transaction to reverse its effect
    cur.execute('SELECT from_account_id, to_account_id, from_amount, to_amount FROM "transaction" WHERE id = %s', (tid,))
    old = cur.fetchone()
    if not old:
        cur.close(); conn.close()
        return jsonify({"error": "not found"}), 404
    cur.execute("""
        UPDATE "transaction" SET from_account_id=%s, to_account_id=%s, category_id=%s,
            project_id=%s, payee_id=%s, note=%s, from_amount=%s, to_amount=%s,
            datetime=%s, status=%s
        WHERE id=%s RETURNING *
    """, (d["from_account_id"], d.get("to_account_id", 0), d.get("category_id", 0),
          d.get("project_id", 0), d.get("payee_id", 0), d.get("note"),
          d["from_amount"], d.get("to_amount", 0), d.get("datetime", now_ms()),
          d.get("status", "UR"), tid))
    row = cur.fetchone()
    # Reverse old, apply new
    update_account_balance(cur, old["from_account_id"], -old["from_amount"])
    update_account_balance(cur, d["from_account_id"], d["from_amount"])
    if old["to_account_id"]:
        update_account_balance(cur, old["to_account_id"], -old["to_amount"])
    if d.get("to_account_id"):
        update_account_balance(cur, d["to_account_id"], d.get("to_amount", 0))
    cur.close(); conn.close()
    return jsonify(row)


@app.route("/api/transactions/<int:tid>", methods=["DELETE"])
def delete_transaction(tid):
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute('SELECT from_account_id, from_amount, to_account_id, to_amount FROM "transaction" WHERE id = %s', (tid,))
    old = cur.fetchone()
    if not old:
        cur.close(); conn.close()
        return jsonify({"error": "not found"}), 404
    cur.execute('DELETE FROM "transaction" WHERE id = %s OR parent_id = %s', (tid, tid))
    update_account_balance(cur, old["from_account_id"], -old["from_amount"])
    if old["to_account_id"]:
        update_account_balance(cur, old["to_account_id"], -(old["to_amount"] or 0))
    cur.close(); conn.close()
    return jsonify({"status": "ok"})


# --- Categories ---
@app.route("/api/categories")
def list_categories():
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute('SELECT * FROM category WHERE is_active = TRUE ORDER BY "left"')
    rows = cur.fetchall()
    cur.close(); conn.close()
    return jsonify(rows)


@app.route("/api/categories", methods=["POST"])
def create_category():
    d = request.json
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    new_id = next_id(cur, "category")
    # Simple append: set left/right at the end
    cur.execute('SELECT COALESCE(MAX("right"), 0) as max_r FROM category')
    max_right = cur.fetchone()["max_r"]
    cur.execute("""
        INSERT INTO category (id, title, "left", "right", type, is_active)
        VALUES (%s, %s, %s, %s, %s, TRUE) RETURNING *
    """, (new_id, d["title"], max_right + 1, max_right + 2, d.get("type", 0)))
    row = cur.fetchone()
    cur.close(); conn.close()
    return jsonify(row), 201


@app.route("/api/categories/<int:cid>", methods=["PUT"])
def update_category(cid):
    d = request.json
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("UPDATE category SET title=%s, type=%s WHERE id=%s RETURNING *",
                (d["title"], d.get("type", 0), cid))
    row = cur.fetchone()
    cur.close(); conn.close()
    if not row:
        return jsonify({"error": "not found"}), 404
    return jsonify(row)


@app.route("/api/categories/<int:cid>", methods=["DELETE"])
def delete_category(cid):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("UPDATE category SET is_active = FALSE WHERE id = %s", (cid,))
    cur.close(); conn.close()
    return jsonify({"status": "ok"})


# --- Payees ---
@app.route("/api/payees")
def list_payees():
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SELECT * FROM payee WHERE is_active = TRUE ORDER BY title")
    rows = cur.fetchall()
    cur.close(); conn.close()
    return jsonify(rows)


@app.route("/api/payees", methods=["POST"])
def create_payee():
    d = request.json
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    new_id = next_id(cur, "payee")
    cur.execute("INSERT INTO payee (id, title, is_active) VALUES (%s, %s, TRUE) RETURNING *",
                (new_id, d["title"]))
    row = cur.fetchone()
    cur.close(); conn.close()
    return jsonify(row), 201


@app.route("/api/payees/<int:pid>", methods=["DELETE"])
def delete_payee(pid):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("UPDATE payee SET is_active = FALSE WHERE id = %s", (pid,))
    cur.close(); conn.close()
    return jsonify({"status": "ok"})


# --- Projects ---
@app.route("/api/projects")
def list_projects():
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SELECT * FROM project WHERE is_active = TRUE ORDER BY title")
    rows = cur.fetchall()
    cur.close(); conn.close()
    return jsonify(rows)


# --- Stats ---
@app.route("/api/stats/monthly")
def monthly_stats():
    account_id = request.args.get("account_id", type=int)
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    where = "WHERE t.parent_id = 0 AND t.is_template = 0 AND t.to_account_id = 0"
    params = []
    if account_id:
        where += " AND t.from_account_id = %s"
        params.append(account_id)
    cur.execute(f"""
        SELECT
            to_char(to_timestamp(t.datetime / 1000), 'YYYY-MM') as month,
            SUM(CASE WHEN t.from_amount > 0 THEN t.from_amount ELSE 0 END) as income,
            SUM(CASE WHEN t.from_amount < 0 THEN t.from_amount ELSE 0 END) as expense
        FROM "transaction" t
        {where}
        GROUP BY month ORDER BY month DESC LIMIT 24
    """, params)
    rows = cur.fetchall()
    cur.close(); conn.close()
    return jsonify(rows)


@app.route("/api/stats/daily")
def daily_stats():
    """Daily totals for a given month."""
    month = request.args.get("month")  # YYYY-MM
    account_id = request.args.get("account_id", type=int)
    if not month:
        return jsonify({"error": "month param required (YYYY-MM)"}), 400
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    where = "WHERE t.parent_id = 0 AND t.is_template = 0 AND t.to_account_id = 0 AND to_char(to_timestamp(t.datetime/1000), 'YYYY-MM') = %s"
    params = [month]
    if account_id:
        where += " AND t.from_account_id = %s"
        params.append(account_id)
    cur.execute(f"""
        SELECT to_char(to_timestamp(t.datetime/1000), 'YYYY-MM-DD') as day,
            SUM(CASE WHEN t.from_amount > 0 THEN t.from_amount ELSE 0 END) as income,
            SUM(CASE WHEN t.from_amount < 0 THEN t.from_amount ELSE 0 END) as expense
        FROM "transaction" t {where}
        GROUP BY day ORDER BY day
    """, params)
    rows = cur.fetchall()
    cur.close(); conn.close()
    return jsonify(rows)


@app.route("/api/stats/daily-by-category")
def daily_by_category():
    """Daily expense breakdown by category for stacked chart."""
    month = request.args.get("month")
    if not month:
        return jsonify({"error": "month param required"}), 400
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("""
        SELECT to_char(to_timestamp(t.datetime/1000), 'YYYY-MM-DD') as day,
            COALESCE(cat.title, 'Altro') as category,
            SUM(ABS(t.from_amount)) as total
        FROM "transaction" t
        LEFT JOIN category cat ON t.category_id = cat.id
        WHERE t.parent_id = 0 AND t.is_template = 0 AND t.to_account_id = 0
            AND t.from_amount < 0
            AND to_char(to_timestamp(t.datetime/1000), 'YYYY-MM') = %s
        GROUP BY day, cat.title ORDER BY day
    """, (month,))
    rows = cur.fetchall()
    cur.close(); conn.close()
    return jsonify(rows)


@app.route("/api/stats/yearly")
def yearly_stats():
    """Yearly income/expense (excluding transfers)."""
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("""
        SELECT to_char(to_timestamp(t.datetime/1000), 'YYYY') as year,
            SUM(CASE WHEN t.from_amount > 0 THEN t.from_amount ELSE 0 END) as income,
            SUM(CASE WHEN t.from_amount < 0 THEN t.from_amount ELSE 0 END) as expense
        FROM "transaction" t
        WHERE t.parent_id = 0 AND t.is_template = 0 AND t.to_account_id = 0
        GROUP BY year ORDER BY year
    """)
    rows = cur.fetchall()
    cur.close(); conn.close()
    return jsonify(rows)


@app.route("/api/stats/by-category")
def stats_by_category():
    """Expense breakdown by category (excluding transfers)."""
    month = request.args.get("month")  # YYYY-MM or YYYY
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    where = "WHERE t.parent_id = 0 AND t.is_template = 0 AND t.from_amount < 0 AND t.to_account_id = 0"
    params = []
    if month and len(month) == 7:
        where += " AND to_char(to_timestamp(t.datetime/1000), 'YYYY-MM') = %s"
        params.append(month)
    elif month and len(month) == 4:
        where += " AND to_char(to_timestamp(t.datetime/1000), 'YYYY') = %s"
        params.append(month)
    cur.execute(f"""
        SELECT COALESCE(cat.title, 'Senza categoria') as category,
            SUM(ABS(t.from_amount)) as total
        FROM "transaction" t
        LEFT JOIN category cat ON t.category_id = cat.id
        {where}
        GROUP BY cat.title ORDER BY total DESC
    """, params)
    rows = cur.fetchall()
    cur.close(); conn.close()
    return jsonify(rows)


@app.route("/api/stats/savings")
def savings_trend():
    """Cumulative savings (excluding transfers)."""
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("""
        SELECT month, income, expense,
            SUM(income + expense) OVER (ORDER BY month) as cumulative_savings
        FROM (
            SELECT to_char(to_timestamp(t.datetime/1000), 'YYYY-MM') as month,
                SUM(CASE WHEN t.from_amount > 0 THEN t.from_amount ELSE 0 END) as income,
                SUM(CASE WHEN t.from_amount < 0 THEN t.from_amount ELSE 0 END) as expense
            FROM "transaction" t
            WHERE t.parent_id = 0 AND t.is_template = 0 AND t.to_account_id = 0
            GROUP BY month
        ) sub ORDER BY month
    """)
    rows = cur.fetchall()
    cur.close(); conn.close()
    return jsonify(rows)


# --- Transactions with filters ---
@app.route("/api/transactions/search")
def search_transactions():
    """Filtered transaction search."""
    limit = request.args.get("limit", 50, type=int)
    offset = request.args.get("offset", 0, type=int)
    account_id = request.args.get("account_id")
    category_id = request.args.get("category_id")
    payee_id = request.args.get("payee_id", type=int)
    date_from = request.args.get("date_from")  # YYYY-MM-DD
    date_to = request.args.get("date_to")      # YYYY-MM-DD
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    where = ["t.parent_id = 0", "t.is_template = 0"]
    params = []
    if account_id:
        ids = [int(x) for x in account_id.split(',')]
        where.append("t.from_account_id = ANY(%s)"); params.append(ids)
    if category_id:
        ids = [int(x) for x in category_id.split(',')]
        where.append("t.category_id = ANY(%s)"); params.append(ids)
    if payee_id:
        where.append("t.payee_id = %s"); params.append(payee_id)
    if date_from:
        where.append("t.datetime >= %s"); params.append(int(datetime_str_to_ms(date_from)))
    if date_to:
        where.append("t.datetime <= %s"); params.append(int(datetime_str_to_ms(date_to) + 86400000))
    where_sql = " AND ".join(where)
    cur.execute(f"""
        SELECT t.*, cat.title as category_title, p.title as payee_title,
               a.title as account_title, cur.symbol as currency_symbol, cur.decimals as currency_decimals
        FROM "transaction" t
        LEFT JOIN category cat ON t.category_id = cat.id
        LEFT JOIN payee p ON t.payee_id = p.id
        LEFT JOIN account a ON t.from_account_id = a.id
        LEFT JOIN currency cur ON a.currency_id = cur.id
        WHERE {where_sql}
        ORDER BY t.datetime DESC LIMIT %s OFFSET %s
    """, params + [limit, offset])
    rows = cur.fetchall()
    cur.close(); conn.close()
    return jsonify(rows)


def datetime_str_to_ms(s):
    """Convert YYYY-MM-DD to epoch ms."""
    import datetime as dt
    d = dt.datetime.strptime(s, "%Y-%m-%d")
    return int(d.timestamp() * 1000)


# --- Export ---
@app.route("/api/export")
def export_json():
    """Export all data as human-readable JSON."""
    import json
    from datetime import datetime as dt
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    cur.execute("SELECT * FROM currency ORDER BY name")
    currencies = cur.fetchall()

    cur.execute("SELECT * FROM account ORDER BY sort_order, title")
    accounts = cur.fetchall()

    cur.execute('SELECT * FROM category WHERE is_active = TRUE ORDER BY "left"')
    categories = cur.fetchall()

    cur.execute("SELECT * FROM payee WHERE is_active = TRUE ORDER BY title")
    payees = cur.fetchall()

    cur.execute("""
        SELECT t.*, cat.title as category_title, p.title as payee_title,
               a.title as account_title
        FROM "transaction" t
        LEFT JOIN category cat ON t.category_id = cat.id
        LEFT JOIN payee p ON t.payee_id = p.id
        LEFT JOIN account a ON t.from_account_id = a.id
        WHERE t.parent_id = 0 AND t.is_template = 0
        ORDER BY t.datetime DESC
    """)
    transactions = cur.fetchall()
    cur.close(); conn.close()

    # Format for readability
    def fmt_tx(t):
        return {
            "id": t["id"],
            "date": dt.fromtimestamp(t["datetime"]/1000).strftime("%Y-%m-%d %H:%M"),
            "account": t["account_title"],
            "amount": t["from_amount"] / 100,
            "category": t["category_title"],
            "payee": t["payee_title"],
            "note": t["note"],
            "is_transfer": t["to_account_id"] > 0,
        }

    def fmt_acc(a):
        cur_info = next((c for c in currencies if c["id"] == a["currency_id"]), {})
        return {
            "id": a["id"],
            "title": a["title"],
            "type": a["type"],
            "balance": a["total_amount"] / 100,
            "currency": cur_info.get("name", "?"),
            "is_active": a["is_active"],
        }

    export = {
        "exported_at": dt.now().strftime("%Y-%m-%d %H:%M:%S"),
        "accounts": [fmt_acc(a) for a in accounts],
        "categories": [{"id": c["id"], "title": c["title"]} for c in categories],
        "payees": [{"id": p["id"], "title": p["title"]} for p in payees],
        "transactions": [fmt_tx(t) for t in transactions],
    }

    response = app.response_class(
        response=json.dumps(export, indent=2, ensure_ascii=False),
        mimetype='application/json',
        headers={"Content-Disposition": "attachment; filename=financisto_export.json"}
    )
    return response


# --- Categories tree ---
@app.route("/api/categories/tree")
def categories_tree():
    """Return categories as a tree structure using nested set model."""
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute('SELECT * FROM category WHERE is_active = TRUE ORDER BY "left"')
    cats = cur.fetchall()
    cur.close(); conn.close()

    # Build tree from nested set
    tree = []
    stack = []
    for c in cats:
        node = {"id": c["id"], "title": c["title"], "left": c["left"], "right": c["right"], "children": []}
        while stack and stack[-1]["right"] < c["left"]:
            stack.pop()
        if stack:
            stack[-1]["children"].append(node)
        else:
            tree.append(node)
        stack.append(node)
    return jsonify(tree)


@app.route("/api/categories/<int:parent_id>/subcategory", methods=["POST"])
def create_subcategory(parent_id):
    """Create a subcategory under a parent."""
    d = request.json
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    # Get parent's right value
    cur.execute('SELECT "right" FROM category WHERE id = %s', (parent_id,))
    parent = cur.fetchone()
    if not parent:
        cur.close(); conn.close()
        return jsonify({"error": "parent not found"}), 404
    parent_right = parent["right"]
    # Make space: shift all nodes to the right
    cur.execute('UPDATE category SET "right" = "right" + 2 WHERE "right" >= %s', (parent_right,))
    cur.execute('UPDATE category SET "left" = "left" + 2 WHERE "left" > %s', (parent_right,))
    # Insert new node
    new_id = next_id(cur, "category")
    cur.execute("""
        INSERT INTO category (id, title, "left", "right", type, is_active)
        VALUES (%s, %s, %s, %s, 0, TRUE) RETURNING *
    """, (new_id, d["title"], parent_right, parent_right + 1))
    row = cur.fetchone()
    cur.close(); conn.close()
    return jsonify(row), 201


# --- Full Database Export/Import ---
@app.route("/api/db/export")
def export_db():
    """Export full database as JSON (reimportable)."""
    import json
    from datetime import datetime as dt
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    tables = ["currency", "category", "project", "payee", "location", "account",
              "transaction", "attribute", "category_attribute", "transaction_attribute",
              "budget", "currency_exchange_rate", "ccard_closing_date"]
    data = {"exported_at": dt.now().isoformat(), "tables": {}}
    for table in tables:
        cur.execute(f'SELECT * FROM "{table}"')
        rows = cur.fetchall()
        # Convert Decimal to float for JSON
        for row in rows:
            for k, v in row.items():
                if hasattr(v, 'as_integer_ratio'):
                    row[k] = float(v)
        data["tables"][table] = rows

    cur.close(); conn.close()
    response = app.response_class(
        response=json.dumps(data, default=str, ensure_ascii=False),
        mimetype='application/json',
        headers={"Content-Disposition": f"attachment; filename=financisto_db_{dt.now().strftime('%Y%m%d_%H%M%S')}.json"}
    )
    return response


@app.route("/api/db/import", methods=["POST"])
def import_db():
    """Import full database from JSON export."""
    import json
    if "file" not in request.files:
        return jsonify({"error": "No file provided"}), 400
    content = request.files["file"].read()
    try:
        data = json.loads(content)
    except json.JSONDecodeError as e:
        return jsonify({"error": f"Invalid JSON: {e}"}), 400

    if "tables" not in data:
        return jsonify({"error": "Invalid format: missing 'tables' key"}), 400

    BOOL_COLUMNS = {"is_default", "is_active", "is_include_into_totals"}

    conn = get_db()
    conn.autocommit = False
    cur = conn.cursor()

    import_order = ["currency", "category", "project", "payee", "location", "account",
                    "transaction", "attribute", "category_attribute", "transaction_attribute",
                    "budget", "currency_exchange_rate", "ccard_closing_date"]
    try:
        for table in reversed(import_order):
            cur.execute(f'DELETE FROM "{table}"')

        summary = {}
        for table in import_order:
            rows = data["tables"].get(table, [])
            if not rows:
                continue
            columns = list(rows[0].keys())
            col_names = ", ".join(f'"{c}"' for c in columns)
            placeholders = ", ".join(["%s"] * len(columns))
            sql = f'INSERT INTO "{table}" ({col_names}) VALUES ({placeholders}) ON CONFLICT DO NOTHING'
            for row in rows:
                values = []
                for c in columns:
                    v = row.get(c)
                    if c in BOOL_COLUMNS and v is not None:
                        v = bool(v)
                    values.append(v)
                cur.execute(sql, tuple(values))
            summary[table] = len(rows)

        conn.commit()
        return jsonify({"status": "ok", "imported": summary})
    except Exception as e:
        conn.rollback()
        return jsonify({"error": str(e)}), 500
    finally:
        cur.close(); conn.close()


# --- Backup to S3 ---
import threading

BACKUP_CONFIG_FILE = "/data/backup_config.json"

def load_backup_config():
    import json
    try:
        with open(BACKUP_CONFIG_FILE) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {"enabled": False, "bucket": "", "region": "eu-west-1", "access_key": "", "secret_key": "", "interval_hours": 24, "prefix": "financisto-backup/"}

def save_backup_config(config):
    import json
    os.makedirs(os.path.dirname(BACKUP_CONFIG_FILE), exist_ok=True)
    with open(BACKUP_CONFIG_FILE, "w") as f:
        json.dump(config, f)

@app.route("/api/backup/config", methods=["GET"])
def get_backup_config():
    config = load_backup_config()
    safe = {**config, "secret_key": "***" if config.get("secret_key") else ""}
    return jsonify(safe)

@app.route("/api/backup/config", methods=["POST"])
def set_backup_config():
    d = request.json
    config = load_backup_config()
    for k in ["enabled", "bucket", "region", "access_key", "secret_key", "interval_hours", "prefix"]:
        if k in d:
            if k == "secret_key" and d[k] == "***":
                continue
            config[k] = d[k]
    save_backup_config(config)
    restart_backup_scheduler(config)
    return jsonify({"status": "ok"})

@app.route("/api/backup/now", methods=["POST"])
def backup_now():
    config = load_backup_config()
    if not config.get("bucket") or not config.get("access_key"):
        return jsonify({"error": "Backup not configured"}), 400
    try:
        result = run_backup(config)
        return jsonify({"status": "ok", "key": result})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

def run_backup(config):
    import json, boto3
    from datetime import datetime as dt
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    tables = ["currency", "category", "project", "payee", "location", "account",
              "transaction", "attribute", "category_attribute", "transaction_attribute",
              "budget", "currency_exchange_rate", "ccard_closing_date"]
    data = {"exported_at": dt.now().isoformat(), "tables": {}}
    for table in tables:
        cur.execute(f'SELECT * FROM "{table}"')
        rows = cur.fetchall()
        for row in rows:
            for k, v in row.items():
                if hasattr(v, 'as_integer_ratio'):
                    row[k] = float(v)
        data["tables"][table] = rows
    cur.close(); conn.close()

    payload = json.dumps(data, default=str, ensure_ascii=False).encode('utf-8')
    s3 = boto3.client('s3', region_name=config["region"],
                      aws_access_key_id=config["access_key"],
                      aws_secret_access_key=config["secret_key"])
    key = f"{config.get('prefix', '')}{dt.now().strftime('%Y%m%d_%H%M%S')}.json"
    s3.put_object(Bucket=config["bucket"], Key=key, Body=payload, ContentType='application/json')
    return key

backup_timer = None
def restart_backup_scheduler(config):
    global backup_timer
    if backup_timer:
        backup_timer.cancel()
    if config.get("enabled") and config.get("bucket"):
        schedule_next_backup(config)

def schedule_next_backup(config):
    global backup_timer
    interval = config.get("interval_hours", 24) * 3600
    def do_backup():
        try:
            key = run_backup(config)
            print(f"[backup] Saved to s3://{config['bucket']}/{key}")
        except Exception as e:
            print(f"[backup] Error: {e}")
        schedule_next_backup(config)
    backup_timer = threading.Timer(interval, do_backup)
    backup_timer.daemon = True
    backup_timer.start()

# Start scheduler on boot
with app.app_context():
    cfg = load_backup_config()
    if cfg.get("enabled"):
        restart_backup_scheduler(cfg)


# --- Logs ---
@app.route("/api/logs")
def get_logs():
    """Get recent docker logs from all services."""
    import subprocess
    service = request.args.get("service", "")
    lines = request.args.get("lines", "50")
    try:
        if service:
            result = subprocess.run(["docker", "logs", f"financisto-web-{service}-1", "--tail", lines],
                                    capture_output=True, text=True, timeout=5)
        else:
            # Get all services
            logs = {}
            for svc in ["backend", "email-worker", "db"]:
                r = subprocess.run(["docker", "logs", f"financisto-web-{svc}-1", "--tail", "20"],
                                   capture_output=True, text=True, timeout=5)
                logs[svc] = (r.stdout + r.stderr).strip().split('\n')[-20:]
            return jsonify(logs)
        return jsonify({"logs": (result.stdout + result.stderr).strip().split('\n')})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
