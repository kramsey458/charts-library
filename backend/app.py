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
            notes_path = date_dir / f"{chart_file.stem}.notes.txt"
            notes = ""
            if notes_path.exists() and notes_path.is_file():
                notes = notes_path.read_text(encoding="utf-8").strip()
            charts.append(
                {
                    "ticker": ticker,
                    "date": date_label,
                    "filename": chart_file.name,
                    "url": f"/api/chart-file/{ticker}/{date_label}/{chart_file.name}",
                    "notes": notes,
                }
            )
    return charts


def build_ticker_stats() -> tuple[list[str], dict[str, int], int]:
    tickers = list_tickers()
    chart_counts: dict[str, int] = {}
    total_charts = 0

    for ticker in tickers:
        ticker_chart_count = len(list_charts_for_ticker(ticker))
        chart_counts[ticker] = ticker_chart_count
        total_charts += ticker_chart_count

    return tickers, chart_counts, total_charts


@app.get("/api/health")
def health():
    return jsonify({"status": "ok"})


@app.get("/api/tickers")
def get_tickers():
    tickers, chart_counts, total_charts = build_ticker_stats()
    return jsonify(
        {
            "tickers": tickers,
            "chart_counts": chart_counts,
            "total_charts": total_charts,
        }
    )


@app.get("/api/charts/<ticker>")
def get_charts(ticker: str):
    return jsonify({"charts": list_charts_for_ticker(ticker)})


@app.post("/api/charts")
def upload_chart():
    ensure_storage()
    ticker = request.form.get("ticker", "").strip().upper()
    date_label = request.form.get("date", "").strip()
    notes = request.form.get("notes", "").strip()
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

    notes_path = target_dir / f"{Path(filename).stem}.notes.txt"
    if notes:
        notes_path.write_text(notes, encoding="utf-8")
    elif notes_path.exists() and notes_path.is_file():
        notes_path.unlink()

    return (
        jsonify(
            {
                "message": "Chart uploaded.",
                "chart": {
                    "ticker": safe_ticker,
                    "date": safe_date,
                    "filename": filename,
                    "url": f"/api/chart-file/{safe_ticker}/{safe_date}/{filename}",
                    "notes": notes,
                },
            }
        ),
        201,
    )


@app.delete("/api/charts/<ticker>/<date_label>/<filename>")
def delete_chart(ticker: str, date_label: str, filename: str):
    chart_path = STORAGE_DIR / ticker / date_label / filename
    if not chart_path.exists() or not chart_path.is_file():
        return jsonify({"error": "Chart not found."}), 404

    chart_path.unlink()
    notes_path = chart_path.parent / f"{chart_path.stem}.notes.txt"
    if notes_path.exists() and notes_path.is_file():
        notes_path.unlink()

    date_dir = chart_path.parent
    ticker_dir = date_dir.parent

    if date_dir.exists() and not any(date_dir.iterdir()):
        date_dir.rmdir()
    if ticker_dir.exists() and not any(ticker_dir.iterdir()):
        ticker_dir.rmdir()

    return jsonify({"message": "Chart deleted."})

@app.get("/api/chart-file/<ticker>/<date_label>/<filename>")
def get_chart_file(ticker: str, date_label: str, filename: str):
    target_dir = STORAGE_DIR / ticker / date_label
    if not target_dir.exists():
        return jsonify({"error": "Chart not found."}), 404
    return send_from_directory(target_dir, filename)


if __name__ == "__main__":
    ensure_storage()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=True)
