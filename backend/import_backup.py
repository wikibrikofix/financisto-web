"""Parser and importer for Financisto .backup files into PostgreSQL."""
import gzip
import io
import os
import psycopg2
from psycopg2.extras import execute_values

# Mapping from Financisto table names to our schema table names
TABLE_MAP = {
    "account": "account",
    "attributes": "attribute",
    "category_attribute": "category_attribute",
    "transaction_attribute": "transaction_attribute",
    "budget": "budget",
    "category": "category",
    "currency": "currency",
    "locations": "location",
    "project": "project",
    "transactions": "transaction",
    "payee": "payee",
    "ccard_closing_date": "ccard_closing_date",
    "currency_exchange_rate": "currency_exchange_rate",
}

# Column mapping: financisto_col -> our_col (only where names differ)
COLUMN_MAP = {
    "attribute": {"name": "title"},
    "location": {"name": "title"},
}

# Columns we keep per table (matching our schema)
SCHEMA_COLUMNS = {
    "currency": {"_id", "name", "title", "symbol", "is_default", "decimals",
                 "decimal_separator", "group_separator", "symbol_format", "is_active"},
    "category": {"_id", "title", "left", "right", "type", "is_active"},
    "project": {"_id", "title", "is_active"},
    "payee": {"_id", "title", "last_category_id", "is_active"},
    "location": {"_id", "title", "datetime", "provider", "accuracy",
                 "latitude", "longitude", "resolved_address", "is_active"},
    "account": {"_id", "title", "creation_date", "currency_id", "total_amount",
                "sort_order", "type", "issuer", "number", "is_active",
                "is_include_into_totals", "last_category_id", "last_account_id",
                "total_limit", "card_issuer", "closing_day", "payment_day",
                "note", "last_transaction_date"},
    "transaction": {"_id", "from_account_id", "to_account_id", "category_id",
                    "project_id", "location_id", "payee_id", "note", "from_amount",
                    "to_amount", "datetime", "original_currency_id",
                    "original_from_amount", "parent_id", "is_template",
                    "template_name", "recurrence", "status", "is_ccard_payment",
                    "last_recurrence"},
    "attribute": {"_id", "type", "title", "list_values", "default_value", "is_active"},
    "category_attribute": {"category_id", "attribute_id"},
    "transaction_attribute": {"transaction_id", "attribute_id", "value"},
    "budget": {"_id", "title", "category_id", "currency_id", "amount",
               "include_subcategories", "start_date", "end_date", "project_id",
               "recur", "recur_num", "is_current", "parent_budget_id"},
    "currency_exchange_rate": {"from_currency_id", "to_currency_id", "rate_date", "rate"},
    "ccard_closing_date": {"account_id", "period", "closing_day"},
}

# Rename _id to id in output
ID_COL = "_id"


def parse_backup(file_content: bytes) -> dict:
    """Parse a Financisto .backup file (gzip or plain text) into records by table."""
    # Detect gzip
    if file_content[:2] == b'\x1f\x8b':
        file_content = gzip.decompress(file_content)

    text = file_content.decode("utf-8")
    lines = text.splitlines()

    records = {}  # table_name -> list of dicts
    current_table = None
    current_record = None

    for line in lines:
        if line.startswith("$ENTITY:"):
            current_table = line[8:].strip()
            current_record = {}
        elif line.strip() == "$$":
            if current_table and current_record:
                target = TABLE_MAP.get(current_table)
                if target:
                    records.setdefault(target, []).append(
                        _clean_record(target, current_record)
                    )
            current_table = None
            current_record = None
        elif current_record is not None and ":" in line:
            col, _, val = line.partition(":")
            current_record[col.strip()] = val

    return records


def _clean_record(table: str, record: dict) -> dict | None:
    """Clean and filter a record to match our schema."""
    # Skip system entities (id <= 0)
    if "_id" in record:
        try:
            if int(record["_id"]) <= 0:
                return None
        except (ValueError, TypeError):
            return None

    # Apply column renames
    col_map = COLUMN_MAP.get(table, {})
    renamed = {}
    for k, v in record.items():
        new_key = col_map.get(k, k)
        renamed[new_key] = v

    # Rename _id -> id
    if "_id" in renamed:
        renamed["id"] = renamed.pop("_id")

    # Filter to only schema columns (using "id" instead of "_id")
    allowed = set()
    for c in SCHEMA_COLUMNS.get(table, set()):
        allowed.add("id" if c == "_id" else c)

    return {k: v for k, v in renamed.items() if k in allowed}


# Import order respects foreign key dependencies
IMPORT_ORDER = [
    "currency", "category", "project", "payee", "location",
    "account", "transaction", "attribute", "category_attribute",
    "transaction_attribute", "budget", "currency_exchange_rate",
    "ccard_closing_date",
]


def import_to_db(records: dict, db_url: str):
    """Import parsed records into PostgreSQL."""
    conn = psycopg2.connect(db_url)
    conn.autocommit = False
    cur = conn.cursor()

    try:
        # Clear existing data in reverse order
        for table in reversed(IMPORT_ORDER):
            cur.execute(f'DELETE FROM "{table}"')

        for table in IMPORT_ORDER:
            rows = [r for r in records.get(table, []) if r is not None]
            if not rows:
                continue

            # Get columns from first row, ensure consistent ordering
            columns = sorted(rows[0].keys())
            # Make sure all rows have same columns
            for row in rows:
                for col in columns:
                    row.setdefault(col, None)

            col_names = ", ".join(f'"{c}"' for c in columns)
            placeholders = ", ".join(["%s"] * len(columns))
            sql = f'INSERT INTO "{table}" ({col_names}) VALUES ({placeholders}) ON CONFLICT DO NOTHING'

            batch = [tuple(row.get(c) for c in columns) for row in rows]
            cur.executemany(sql, batch)
            print(f"  {table}: {len(batch)} records")

        conn.commit()
        print("Import completed successfully.")
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        cur.close()
        conn.close()


def run_import(file_path: str, db_url: str):
    """Main entry point: parse file and import."""
    with open(file_path, "rb") as f:
        content = f.read()
    records = parse_backup(content)
    import_to_db(records, db_url)


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python import_backup.py <backup_file> [DATABASE_URL]")
        sys.exit(1)
    file_path = sys.argv[1]
    db_url = sys.argv[2] if len(sys.argv) > 2 else os.environ.get(
        "DATABASE_URL", "postgresql://financisto:financisto@localhost:5432/financisto"
    )
    run_import(file_path, db_url)
