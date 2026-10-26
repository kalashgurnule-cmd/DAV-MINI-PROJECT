"""Flask REST API + static frontend serving.

Every route returns JSON (except / and /static/* which serve the dashboard).
Analytics modules each own their computations; this file only wires them.
"""
from __future__ import annotations

import pandas as pd
from flask import Flask, jsonify, request, send_from_directory

import config
from backend import database
from backend.analytics import charts_data, health_score, inflation, overview, zombies
from backend.seed import (ingest_csv_rows, ingest_sms, ingest_sms_bulk,
                          reseed)

app = Flask(__name__, static_folder=str(config.FRONTEND_DIR), static_url_path="/static")


# ----------------------------------------------------------------- page ----
@app.get("/")
def index():
    return send_from_directory(str(config.FRONTEND_DIR), "index.html")


# ----------------------------------------------------------------- data APIs ----
@app.get("/api/overview")
def api_overview():
    try:
        return jsonify(overview.compute_overview())
    except Exception as exc:  # keep the dashboard alive with a readable error
        return jsonify({"error": str(exc)}), 500


@app.get("/api/zombies")
def api_zombies():
    try:
        return jsonify(zombies.compute_zombies())
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@app.get("/api/charts")
def api_charts():
    """Chart payload: daily/weekly spend, category-months, merchants,
    forecast, budgets, waterfall (feeds the visualization layer)."""
    try:
        return jsonify(charts_data.compute_chart_data())
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@app.get("/api/inflation")
def api_inflation():
    try:
        return jsonify(inflation.compute_inflation())
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@app.get("/api/health-score")
def api_health_score():
    try:
        df = database.load_df()
        return jsonify(health_score.compute_health_score_with_debt(df))
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@app.get("/api/transactions")
def api_transactions():
    try:
        limit = request.args.get("limit", default=5000, type=int)
        with database._Session() as s:
            rows = s.query(database.Transaction).order_by(
                database.Transaction.txn_date.desc()).limit(limit).all()
        return jsonify([r.as_dict() for r in rows])
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


# ----------------------------------------------------------------- ingest APIs ----
@app.post("/api/ingest-sms")
def api_ingest_sms():
    body = request.get_json(silent=True) or {}
    text = (body.get("text") or "").strip()
    if not text:
        return jsonify({"error": "No SMS text received."}), 400
    report = ingest_sms(text)
    report["stored_total"] = database.row_count()
    return jsonify(report)


@app.post("/api/ingest-sms-file")
def api_ingest_sms_file():
    """Bulk door: upload a whole exported SMS dump — txt / XML backup /
    CSV/TSV / JSON / ZIP archive / Android mmssms.db SQLite."""
    file = request.files.get("file")
    if file is None or not file.filename:
        return jsonify({"error": "No SMS file received."}), 400
    raw = file.stream.read()                      # bytes; format sniffing in seed.py
    try:
        report = ingest_sms_bulk(raw, file.filename)
    except ValueError as exc:                     # friendly format errors
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"error": f"Could not read dump: {exc}"}), 500
    report["file"] = file.filename
    report["stored_total"] = database.row_count()
    return jsonify(report)


@app.post("/api/upload-csv")
def api_upload_csv():
    file = request.files.get("file")
    if file is None or not file.filename:
        return jsonify({"error": "No CSV file received."}), 400
    try:
        df_csv = pd.read_csv(file.stream)
        report = ingest_csv_rows(df_csv, file.filename)
        report["stored_total"] = database.row_count()
        return jsonify(report)
    except ValueError as exc:          # friendly schema errors
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@app.post("/api/reset")
def api_reset():
    """Explicit 'load demo dataset' button — never automatic."""
    try:
        seed = request.get_json(silent=True) or {}
        report = reseed(seed.get("seed"))
        return jsonify(report)
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@app.post("/api/clear")
def api_clear():
    """Wipe all stored transactions so the app is empty again."""
    try:
        database.reset_db()
        return jsonify({"cleared": True, "stored_total": 0})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


# ----------------------------------------------------------------- boot ----
if __name__ == "__main__":
    app.run(host=config.HOST, port=config.PORT, debug=False)
