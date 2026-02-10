from __future__ import annotations

import datetime
import os
from pathlib import Path

from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS
from werkzeug.utils import secure_filename

BASE_DIR = Path(__file__).resolve().parent
STORAGE_DIR = BASE_DIR / "storage"
ALLOWED_EXTENSIONS = {"png"}

app = Flask(__name__)
CORS(app)


def allowed_file(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def ensure_storage() -> None:
    STORAGE_DIR.mkdir(parents=True, exist_ok=True)


def list_tickers() -> list[str]:
    ensure_storage()
    return sorted([path.name for path in STORAGE_DIR.iterdir() if path.is_dir()])


def list_charts_for_ticker(ticker: str) -> list[dict]:
    ensure_storage()
    ticker_dir = STORAGE_DIR / ticker
    if not ticker_dir.exists():
        return []

    charts: list[dict] = []
    for date_dir in sorted(ticker_dir.iterdir(), reverse=True):
        if not date_dir.is_dir():
            continue
        date_label = date_dir.name
        for chart_file in sorted(date_dir.glob("*.png")):
            charts.append(
                {
                    "ticker": ticker,
                    "date": date_label,
                    "filename": chart_file.name,
                    "url": f"/api/chart-file/{ticker}/{date_label}/{chart_file.name}",
                }
            )
    return charts


@app.get("/api/health")
def health():
    return jsonify({"status": "ok"})


@app.get("/api/tickers")
def get_tickers():
    return jsonify({"tickers": list_tickers()})


@app.get("/api/charts/<ticker>")
def get_charts(ticker: str):
    return jsonify({"charts": list_charts_for_ticker(ticker)})


@app.post("/api/charts")
def upload_chart():
    ensure_storage()
    ticker = request.form.get("ticker", "").strip().upper()
    date_label = request.form.get("date", "").strip()
    chart_file = request.files.get("chart")

    if not ticker:
        return jsonify({"error": "Ticker is required."}), 400
    if not chart_file or chart_file.filename == "":
        return jsonify({"error": "Chart image is required."}), 400
    if not allowed_file(chart_file.filename):
        return jsonify({"error": "Only PNG files are supported."}), 400

    if not date_label:
        date_label = datetime.date.today().isoformat()

    safe_ticker = secure_filename(ticker)
    safe_date = secure_filename(date_label)
    filename = secure_filename(chart_file.filename)

    target_dir = STORAGE_DIR / safe_ticker / safe_date
    target_dir.mkdir(parents=True, exist_ok=True)

    target_path = target_dir / filename
    chart_file.save(target_path)

    return (
        jsonify(
            {
                "message": "Chart uploaded.",
                "chart": {
                    "ticker": safe_ticker,
                    "date": safe_date,
                    "filename": filename,
                    "url": f"/api/chart-file/{safe_ticker}/{safe_date}/{filename}",
                },
            }
        ),
        201,
    )


@app.get("/api/chart-file/<ticker>/<date_label>/<filename>")
def get_chart_file(ticker: str, date_label: str, filename: str):
    target_dir = STORAGE_DIR / ticker / date_label
    if not target_dir.exists():
        return jsonify({"error": "Chart not found."}), 404
    return send_from_directory(target_dir, filename)


if __name__ == "__main__":
    ensure_storage()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=True)
