"""
routes/csv_io.py — CSV export and import for transactions.

Routes:  GET  /api/transactions/export?month=YYYY-MM   → download CSV
         POST /api/transactions/import                  → upload CSV
"""

import csv
import io
import logging
from datetime import datetime, date

from flask import Blueprint, jsonify, request, session, Response

from auth import login_required
from database import get_cursor

logger = logging.getLogger(__name__)

csv_bp = Blueprint("csv_io", __name__)

# Canonical column order used for both export and import
CSV_FIELDS = ["date", "type", "amount", "currency", "category", "note"]

VALID_TYPES      = {"income", "expense"}
VALID_CURRENCIES = {
    "USD","EUR","GBP","INR","JPY","CAD","AUD","AED",
    "SGD","CHF","CNY","MXN","BRL","KRW","THB",
}


# ── Export ─────────────────────────────────────────────────────────────────────

@csv_bp.route("/api/transactions/export")
@login_required
def export_csv():
    """
    Download all transactions for a given month (or all time) as a CSV file.
    ?month=YYYY-MM   → single month   (default: current month)
    ?month=all       → every transaction the user has ever entered
    """
    month = request.args.get("month", datetime.now().strftime("%Y-%m"))

    try:
        with get_cursor(dict_cursor=True) as (_, cur):
            if month == "all":
                cur.execute(
                    "SELECT date, type, amount, currency, category, note "
                    "FROM transactions WHERE user_id=%s ORDER BY date DESC, id DESC",
                    (session["user_id"],)
                )
                filename = "vault_all_transactions.csv"
            else:
                cur.execute(
                    "SELECT date, type, amount, currency, category, note "
                    "FROM transactions WHERE user_id=%s AND date LIKE %s "
                    "ORDER BY date DESC, id DESC",
                    (session["user_id"], f"{month}%")
                )
                filename = f"vault_{month}.csv"
            rows = cur.fetchall()
    except Exception as e:
        logger.error("export_csv error: %s", e)
        return jsonify({"error": "Could not export transactions."}), 500

    # Build CSV in memory
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=CSV_FIELDS, extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        writer.writerow({
            "date":     row["date"],
            "type":     row["type"],
            "amount":   float(row["amount"]),
            "currency": row["currency"] or "USD",
            "category": row["category"] or "",
            "note":     row["note"] or "",
        })

    csv_bytes = output.getvalue().encode("utf-8")
    return Response(
        csv_bytes,
        mimetype="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ── Import ─────────────────────────────────────────────────────────────────────

@csv_bp.route("/api/transactions/import", methods=["POST"])
@login_required
def import_csv():
    """
    Accept a CSV file upload.  Rows that pass validation are inserted;
    invalid rows are skipped and reported back to the client.

    Expected columns (case-insensitive, order-independent):
        date, type, amount, currency, category, note

    Returns JSON:
        { imported: N, skipped: N, errors: ["row 3: ..."] }
    """
    if "file" not in request.files:
        return jsonify({"error": "No file uploaded"}), 400

    file = request.files["file"]
    if not file.filename.lower().endswith(".csv"):
        return jsonify({"error": "File must be a .csv"}), 400

    try:
        content = file.read().decode("utf-8-sig")   # utf-8-sig strips Excel BOM
    except UnicodeDecodeError:
        return jsonify({"error": "File must be UTF-8 encoded"}), 400

    reader = csv.DictReader(io.StringIO(content))
    # Normalise header names to lowercase, strip whitespace
    if reader.fieldnames is None:
        return jsonify({"error": "CSV appears to be empty"}), 400

    reader.fieldnames = [f.strip().lower() for f in reader.fieldnames]
    required = {"date", "type", "amount"}
    missing  = required - set(reader.fieldnames)
    if missing:
        return jsonify({"error": f"CSV is missing required columns: {', '.join(sorted(missing))}"}), 400

    imported = 0
    skipped  = 0
    errors   = []

    rows_to_insert = []
    for i, row in enumerate(reader, start=2):   # start=2 because row 1 is the header
        # ── Validate date ──
        raw_date = row.get("date", "").strip()
        try:
            parsed = datetime.strptime(raw_date, "%Y-%m-%d").date()
            tx_date = str(parsed)
        except ValueError:
            errors.append(f"Row {i}: invalid date '{raw_date}' — expected YYYY-MM-DD")
            skipped += 1
            continue

        # ── Validate type ──
        tx_type = row.get("type", "").strip().lower()
        if tx_type not in VALID_TYPES:
            errors.append(f"Row {i}: type must be 'income' or 'expense', got '{tx_type}'")
            skipped += 1
            continue

        # ── Validate amount ──
        try:
            amount = float(row.get("amount", "").strip())
            if amount <= 0:
                raise ValueError()
        except (ValueError, AttributeError):
            errors.append(f"Row {i}: amount must be a positive number")
            skipped += 1
            continue

        # ── Optional fields ──
        currency = row.get("currency", "USD").strip().upper() or "USD"
        if currency not in VALID_CURRENCIES:
            currency = "USD"   # silently fall back rather than skip the whole row

        category = row.get("category", "").strip() or ("Income" if tx_type == "income" else "Other")
        note     = row.get("note", "").strip()

        rows_to_insert.append((session["user_id"], tx_type, amount, currency, category, note, tx_date))

    # Bulk insert all valid rows in one transaction
    if rows_to_insert:
        try:
            with get_cursor() as (_, cur):
                cur.executemany(
                    "INSERT INTO transactions (user_id, type, amount, currency, category, note, date) "
                    "VALUES (%s,%s,%s,%s,%s,%s,%s)",
                    rows_to_insert
                )
            imported = len(rows_to_insert)
        except Exception as e:
            logger.error("import_csv DB error: %s", e)
            return jsonify({"error": "Database error while importing. No rows were saved."}), 500

    return jsonify({
        "imported": imported,
        "skipped":  skipped,
        "errors":   errors[:20],   # cap at 20 so response stays readable
    })
