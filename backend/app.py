from __future__ import annotations

import datetime
import hashlib
import os
from pathlib import Path
from typing import Any
from urllib.parse import quote, unquote

import requests
from flask import Flask, jsonify, redirect, request, send_from_directory
from flask_cors import CORS
from werkzeug.utils import secure_filename

BASE_DIR = Path(__file__).resolve().parent
STORAGE_DIR = Path(os.environ.get("LOCAL_STORAGE_DIR", BASE_DIR / "storage"))
ALLOWED_EXTENSIONS = {"png"}
STORAGE_MODE = os.environ.get("STORAGE_MODE", "local").strip().lower()

CLOUDINARY_CLOUD_NAME = os.environ.get("CLOUDINARY_CLOUD_NAME", "").strip()
CLOUDINARY_API_KEY = os.environ.get("CLOUDINARY_API_KEY", "").strip()
CLOUDINARY_API_SECRET = os.environ.get("CLOUDINARY_API_SECRET", "").strip()
CLOUDINARY_FOLDER = os.environ.get("CLOUDINARY_FOLDER", "charts-library").strip().strip("/")

app = Flask(__name__)
CORS(app)


def allowed_file(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def ensure_storage() -> None:
    STORAGE_DIR.mkdir(parents=True, exist_ok=True)


def ensure_external_config() -> tuple[bool, tuple[dict, int] | None]:
    if STORAGE_MODE != "external":
        return True, None
    if CLOUDINARY_CLOUD_NAME and CLOUDINARY_API_KEY and CLOUDINARY_API_SECRET:
        return True, None
    return False, (
        {
            "error": (
                "Cloudinary credentials are missing. Set CLOUDINARY_CLOUD_NAME, "
                "CLOUDINARY_API_KEY, and CLOUDINARY_API_SECRET."
            )
        },
        500,
    )


def list_tickers_local() -> list[str]:
    ensure_storage()
    return sorted([path.name for path in STORAGE_DIR.iterdir() if path.is_dir()])


def list_charts_for_ticker_local(ticker: str) -> list[dict]:
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


def cloudinary_signature(params: dict[str, Any]) -> str:
    pairs = []
    for key in sorted(params.keys()):
        value = params[key]
        if value is None:
            continue
        value_str = str(value)
        if value_str == "":
            continue
        pairs.append(f"{key}={value_str}")
    payload = "&".join(pairs)
    return hashlib.sha1(f"{payload}{CLOUDINARY_API_SECRET}".encode("utf-8")).hexdigest()


def cloudinary_admin_get(path: str, params: dict[str, Any]) -> dict[str, Any]:
    url = f"https://api.cloudinary.com/v1_1/{CLOUDINARY_CLOUD_NAME}/{path}"
    response = requests.get(url, params=params, auth=(CLOUDINARY_API_KEY, CLOUDINARY_API_SECRET), timeout=30)
    if response.status_code >= 400:
        message = response.json().get("error", {}).get("message") if response.headers.get("content-type", "").startswith("application/json") else "Cloudinary admin request failed."
        raise RuntimeError(message or "Cloudinary admin request failed.")
    return response.json()


def list_all_charts_external() -> list[dict[str, Any]]:
    resources: list[dict[str, Any]] = []
    next_cursor = ""

    while True:
        payload = cloudinary_admin_get(
            "resources/image/upload",
            {
                "prefix": f"{CLOUDINARY_FOLDER}/",
                "context": "true",
                "max_results": 500,
                "next_cursor": next_cursor,
            },
        )
        resources.extend(payload.get("resources", []))
        next_cursor = payload.get("next_cursor", "")
        if not next_cursor:
            break

    charts: list[dict[str, Any]] = []
    for resource in resources:
        context = ((resource.get("context") or {}).get("custom") or {})
        ticker = str(context.get("ticker", "")).strip().upper()
        date_label = str(context.get("date", "")).strip()
        filename = str(context.get("filename", "")).strip()
        if not ticker or not date_label or not filename:
            continue

        notes = str(context.get("notes", ""))
        try:
            notes = unquote(notes)
        except Exception:
            pass

        charts.append(
            {
                "ticker": ticker,
                "date": date_label,
                "filename": filename,
                "notes": notes,
                "public_id": resource.get("public_id", ""),
                "secure_url": resource.get("secure_url", ""),
                "created_at": resource.get("created_at", ""),
            }
        )

    charts.sort(
        key=lambda c: (
            c["ticker"],
            c["date"],
            c["filename"],
            c["created_at"],
        ),
        reverse=False,
    )
    return charts


def build_chart_stats_external() -> tuple[list[str], dict[str, int], int]:
    charts = list_all_charts_external()
    chart_counts: dict[str, int] = {}
    for chart in charts:
        chart_counts[chart["ticker"]] = chart_counts.get(chart["ticker"], 0) + 1
    tickers = sorted(chart_counts.keys())
    return tickers, chart_counts, len(charts)


def upload_chart_external(ticker: str, date_label: str, filename: str, notes: str, chart_file) -> None:
    timestamp = int(datetime.datetime.now(datetime.timezone.utc).timestamp())
    folder = f"{CLOUDINARY_FOLDER}/{ticker}/{date_label}"
    base_name = Path(filename).stem
    safe_base_name = secure_filename(base_name) or "chart"
    public_id = f"{folder}/{safe_base_name}"
    context = f"ticker={ticker}|date={date_label}|filename={filename}|notes={quote(notes)}"

    signature = cloudinary_signature(
        {
            "context": context,
            "overwrite": "true",
            "public_id": public_id,
            "timestamp": timestamp,
        }
    )

    upload_url = f"https://api.cloudinary.com/v1_1/{CLOUDINARY_CLOUD_NAME}/image/upload"
    chart_file.stream.seek(0)
    files = {
        "file": (filename, chart_file.stream, chart_file.mimetype or "image/png"),
    }
    data = {
        "api_key": CLOUDINARY_API_KEY,
        "timestamp": str(timestamp),
        "signature": signature,
        "public_id": public_id,
        "overwrite": "true",
        "context": context,
    }
    response = requests.post(upload_url, data=data, files=files, timeout=60)
    if response.status_code >= 400:
        message = response.json().get("error", {}).get("message") if response.headers.get("content-type", "").startswith("application/json") else "Cloudinary upload failed."
        raise RuntimeError(message or "Cloudinary upload failed.")




def update_chart_notes_external(public_id: str, ticker: str, date_label: str, filename: str, notes: str) -> None:
    timestamp = int(datetime.datetime.now(datetime.timezone.utc).timestamp())
    context = f"ticker={ticker}|date={date_label}|filename={filename}|notes={quote(notes)}"
    signature = cloudinary_signature(
        {
            "context": context,
            "public_id": public_id,
            "timestamp": timestamp,
            "type": "upload",
        }
    )
    explicit_url = f"https://api.cloudinary.com/v1_1/{CLOUDINARY_CLOUD_NAME}/image/explicit"
    response = requests.post(
        explicit_url,
        data={
            "public_id": public_id,
            "type": "upload",
            "api_key": CLOUDINARY_API_KEY,
            "timestamp": str(timestamp),
            "signature": signature,
            "context": context,
        },
        timeout=30,
    )
    if response.status_code >= 400:
        message = response.json().get("error", {}).get("message") if response.headers.get("content-type", "").startswith("application/json") else "Cloudinary note update failed."
        raise RuntimeError(message or "Cloudinary note update failed.")

def delete_chart_external(public_id: str) -> None:
    timestamp = int(datetime.datetime.now(datetime.timezone.utc).timestamp())
    signature = cloudinary_signature({"public_id": public_id, "timestamp": timestamp})
    destroy_url = f"https://api.cloudinary.com/v1_1/{CLOUDINARY_CLOUD_NAME}/image/destroy"
    response = requests.post(
        destroy_url,
        data={
            "public_id": public_id,
            "api_key": CLOUDINARY_API_KEY,
            "timestamp": str(timestamp),
            "signature": signature,
        },
        timeout=30,
    )
    if response.status_code >= 400:
        message = response.json().get("error", {}).get("message") if response.headers.get("content-type", "").startswith("application/json") else "Cloudinary delete failed."
        raise RuntimeError(message or "Cloudinary delete failed.")


def build_ticker_stats() -> tuple[list[str], dict[str, int], int]:
    if STORAGE_MODE == "external":
        return build_chart_stats_external()

    tickers = list_tickers_local()
    chart_counts: dict[str, int] = {}
    total_charts = 0

    for ticker in tickers:
        ticker_chart_count = len(list_charts_for_ticker_local(ticker))
        chart_counts[ticker] = ticker_chart_count
        total_charts += ticker_chart_count

    return tickers, chart_counts, total_charts


@app.get("/api/health")
def health():
    payload = {"status": "ok", "storage_mode": STORAGE_MODE}
    if STORAGE_MODE == "external":
        payload["provider"] = "cloudinary"
    return jsonify(payload)


@app.get("/api/tickers")
def get_tickers():
    is_ok, err = ensure_external_config()
    if not is_ok:
        payload, status = err
        return jsonify(payload), status

    try:
        tickers, chart_counts, total_charts = build_ticker_stats()
    except RuntimeError as exc:
        return jsonify({"error": str(exc)}), 502

    return jsonify(
        {
            "tickers": tickers,
            "chart_counts": chart_counts,
            "total_charts": total_charts,
        }
    )


@app.get("/api/charts/<ticker>")
def get_charts(ticker: str):
    is_ok, err = ensure_external_config()
    if not is_ok:
        payload, status = err
        return jsonify(payload), status

    normalized_ticker = ticker.strip().upper()

    if STORAGE_MODE == "external":
        try:
            charts = [
                {
                    "ticker": c["ticker"],
                    "date": c["date"],
                    "filename": c["filename"],
                    "url": f"/api/chart-file/{c['ticker']}/{c['date']}/{c['filename']}",
                    "notes": c.get("notes", ""),
                }
                for c in list_all_charts_external()
                if c["ticker"] == normalized_ticker
            ]
            charts.sort(key=lambda c: c["date"], reverse=True)
            return jsonify({"charts": charts})
        except RuntimeError as exc:
            return jsonify({"error": str(exc)}), 502

    return jsonify({"charts": list_charts_for_ticker_local(normalized_ticker)})


@app.post("/api/charts")
def upload_chart():
    is_ok, err = ensure_external_config()
    if not is_ok:
        payload, status = err
        return jsonify(payload), status

    if STORAGE_MODE == "local":
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

    if STORAGE_MODE == "external":
        try:
            upload_chart_external(safe_ticker, safe_date, filename, notes, chart_file)
        except RuntimeError as exc:
            return jsonify({"error": str(exc)}), 502
    else:
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
    is_ok, err = ensure_external_config()
    if not is_ok:
        payload, status = err
        return jsonify(payload), status

    normalized_ticker = ticker.strip().upper()

    if STORAGE_MODE == "external":
        try:
            chart = next(
                (
                    c
                    for c in list_all_charts_external()
                    if c["ticker"] == normalized_ticker
                    and c["date"] == date_label
                    and c["filename"] == filename
                ),
                None,
            )
            if not chart:
                return jsonify({"error": "Chart not found."}), 404
            delete_chart_external(chart["public_id"])
            return jsonify({"message": "Chart deleted."})
        except RuntimeError as exc:
            return jsonify({"error": str(exc)}), 502

    chart_path = STORAGE_DIR / normalized_ticker / date_label / filename
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




@app.patch("/api/charts/<ticker>/<date_label>/<filename>/notes")
def update_chart_notes(ticker: str, date_label: str, filename: str):
    is_ok, err = ensure_external_config()
    if not is_ok:
        payload, status = err
        return jsonify(payload), status

    normalized_ticker = ticker.strip().upper()
    payload = request.get_json(silent=True) or {}
    notes = str(payload.get("notes", "")).strip()

    if STORAGE_MODE == "external":
        try:
            chart = next(
                (
                    c
                    for c in list_all_charts_external()
                    if c["ticker"] == normalized_ticker
                    and c["date"] == date_label
                    and c["filename"] == filename
                ),
                None,
            )
            if not chart:
                return jsonify({"error": "Chart not found."}), 404
            update_chart_notes_external(chart["public_id"], normalized_ticker, date_label, filename, notes)
            return jsonify(
                {
                    "message": "Notes updated.",
                    "chart": {
                        "ticker": normalized_ticker,
                        "date": date_label,
                        "filename": filename,
                        "notes": notes,
                    },
                }
            )
        except RuntimeError as exc:
            return jsonify({"error": str(exc)}), 502

    chart_path = STORAGE_DIR / normalized_ticker / date_label / filename
    if not chart_path.exists() or not chart_path.is_file():
        return jsonify({"error": "Chart not found."}), 404

    notes_path = chart_path.parent / f"{chart_path.stem}.notes.txt"
    if notes:
        notes_path.write_text(notes, encoding="utf-8")
    elif notes_path.exists() and notes_path.is_file():
        notes_path.unlink()

    return jsonify(
        {
            "message": "Notes updated.",
            "chart": {
                "ticker": normalized_ticker,
                "date": date_label,
                "filename": filename,
                "notes": notes,
            },
        }
    )

@app.get("/api/chart-file/<ticker>/<date_label>/<filename>")
def get_chart_file(ticker: str, date_label: str, filename: str):
    is_ok, err = ensure_external_config()
    if not is_ok:
        payload, status = err
        return jsonify(payload), status

    normalized_ticker = ticker.strip().upper()

    if STORAGE_MODE == "external":
        try:
            chart = next(
                (
                    c
                    for c in list_all_charts_external()
                    if c["ticker"] == normalized_ticker
                    and c["date"] == date_label
                    and c["filename"] == filename
                ),
                None,
            )
            if not chart or not chart.get("secure_url"):
                return jsonify({"error": "Chart not found."}), 404
            return redirect(chart["secure_url"], code=302)
        except RuntimeError as exc:
            return jsonify({"error": str(exc)}), 502

    target_dir = STORAGE_DIR / normalized_ticker / date_label
    if not target_dir.exists():
        return jsonify({"error": "Chart not found."}), 404
    return send_from_directory(target_dir, filename)


if __name__ == "__main__":
    if STORAGE_MODE == "local":
        ensure_storage()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=True)
