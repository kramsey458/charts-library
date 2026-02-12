from __future__ import annotations

import datetime
from pathlib import Path

from werkzeug.utils import secure_filename

from .checklist import CHECKLIST_KEYS, sanitize_checklist
from .cloudinary_storage import CloudinaryStorage
from .config import Settings
from .local_storage import LocalStorage


class ChartService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.local = LocalStorage(settings.storage_dir)
        self.external = CloudinaryStorage(
            cloud_name=settings.cloudinary_cloud_name,
            api_key=settings.cloudinary_api_key,
            api_secret=settings.cloudinary_api_secret,
            folder=settings.cloudinary_folder,
        )

    @property
    def is_external(self) -> bool:
        return self.settings.is_external

    def validate_external_config(self) -> tuple[bool, tuple[dict, int] | None]:
        if not self.is_external:
            return True, None
        if self.external.has_credentials():
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

    def allowed_file(self, filename: str) -> bool:
        return "." in filename and filename.rsplit(".", 1)[1].lower() in self.settings.allowed_extensions

    def build_ticker_stats(self) -> tuple[list[str], dict[str, int], int]:
        if self.is_external:
            charts = self.external.list_all_charts()
            counts: dict[str, int] = {}
            for chart in charts:
                counts[chart["ticker"]] = counts.get(chart["ticker"], 0) + 1
            return sorted(counts.keys()), counts, len(charts)

        tickers = self.local.list_tickers()
        counts: dict[str, int] = {}
        total = 0
        for ticker in tickers:
            count = len(self.local.list_charts_for_ticker(ticker))
            counts[ticker] = count
            total += count
        return tickers, counts, total

    def list_charts(self, ticker: str) -> list[dict]:
        normalized_ticker = ticker.strip().upper()
        if self.is_external:
            charts = [
                self.external.chart_payload(chart)
                for chart in self.external.list_all_charts()
                if chart["ticker"] == normalized_ticker
            ]
            charts.sort(key=lambda c: c["date"], reverse=True)
            return charts

        return self.local.list_charts_for_ticker(normalized_ticker)


    @staticmethod
    def merge_candle_classification_into_checklist(checklist: dict, label: str | None) -> dict:
        merged = {**checklist}
        if label == "red":
            merged["red_candle"] = True
            merged["yellow_candle"] = False
        elif label == "yellow":
            merged["yellow_candle"] = True
            merged["red_candle"] = False
        else:
            merged["red_candle"] = False
            merged["yellow_candle"] = False
        return merged

    def classify_chart_file(self, chart_file) -> dict:
        image_bytes = chart_file.read()
        chart_file.stream.seek(0)
        from .candle_classifier import classify_candle

        return classify_candle(image_bytes)

    def upload_chart(self, form, files, image_field_names: tuple[str, ...] = ("chart",)) -> tuple[dict, int]:
        if not self.is_external:
            self.local.ensure_storage()

        ticker = form.get("ticker", "").strip().upper()
        date_label = form.get("date", "").strip() or datetime.date.today().isoformat()
        notes = form.get("notes", "").strip()
        checklist = sanitize_checklist({key: form.get(key, "") for key in CHECKLIST_KEYS})
        classification: dict | None = None
        chart_file = next((files.get(field_name) for field_name in image_field_names if files.get(field_name)), None)

        if not ticker:
            return {"error": "Ticker is required."}, 400
        if not chart_file or chart_file.filename == "":
            return {"error": "Chart image is required."}, 400
        if not self.allowed_file(chart_file.filename):
            return {"error": "Only PNG files are supported."}, 400

        safe_ticker = secure_filename(ticker)
        safe_date = secure_filename(date_label)
        filename = secure_filename(chart_file.filename)

        if self.settings.auto_classify_candle:
            classification = self.classify_chart_file(chart_file)
            checklist = self.merge_candle_classification_into_checklist(checklist, classification.get("label"))

        if self.is_external:
            self.external.upload_chart(safe_ticker, safe_date, filename, notes, checklist, chart_file)
        else:
            self.local.save_chart(safe_ticker, safe_date, filename, notes, checklist, chart_file)

        response = {
            "message": "Chart uploaded.",
            "chart": {
                "ticker": safe_ticker,
                "date": safe_date,
                "filename": filename,
                "url": f"/api/chart-file/{safe_ticker}/{safe_date}/{filename}",
                "notes": notes,
                "checklist": checklist,
            },
        }
        if classification is not None:
            response["classification"] = classification
        return response, 201


    def classify_chart_upload(self, files, image_field_names: tuple[str, ...] = ("chart", "image")) -> tuple[dict, int]:
        chart_file = next((files.get(field_name) for field_name in image_field_names if files.get(field_name)), None)
        if not chart_file or chart_file.filename == "":
            return {"error": "Chart image is required."}, 400
        if not self.allowed_file(chart_file.filename):
            return {"error": "Only PNG files are supported."}, 400

        classification = self.classify_chart_file(chart_file)
        checklist = self.merge_candle_classification_into_checklist(
            sanitize_checklist({key: False for key in CHECKLIST_KEYS}),
            classification.get("label"),
        )
        return {"classification": classification, "checklist": checklist}, 200

    def delete_chart(self, ticker: str, date_label: str, filename: str) -> tuple[dict, int]:
        normalized_ticker = ticker.strip().upper()

        if self.is_external:
            chart = next(
                (
                    c
                    for c in self.external.list_all_charts()
                    if c["ticker"] == normalized_ticker and c["date"] == date_label and c["filename"] == filename
                ),
                None,
            )
            if not chart:
                return {"error": "Chart not found."}, 404
            self.external.delete_chart(chart["public_id"])
            return {"message": "Chart deleted."}, 200

        was_deleted = self.local.delete_chart(normalized_ticker, date_label, filename)
        if not was_deleted:
            return {"error": "Chart not found."}, 404
        return {"message": "Chart deleted."}, 200

    def update_notes(self, ticker: str, date_label: str, filename: str, payload: dict) -> tuple[dict, int]:
        normalized_ticker = ticker.strip().upper()
        notes = str(payload.get("notes", "")).strip()
        checklist_payload = payload.get("checklist") if isinstance(payload, dict) else None
        has_checklist_payload = isinstance(checklist_payload, dict)

        if self.is_external:
            chart = next(
                (
                    c
                    for c in self.external.list_all_charts()
                    if c["ticker"] == normalized_ticker and c["date"] == date_label and c["filename"] == filename
                ),
                None,
            )
            if not chart:
                return {"error": "Chart not found."}, 404
            checklist = sanitize_checklist(checklist_payload) if has_checklist_payload else sanitize_checklist(chart.get("checklist"))
            self.external.update_chart_notes(chart["public_id"], normalized_ticker, date_label, filename, notes, checklist)
        else:
            chart_path = self.settings.storage_dir / normalized_ticker / date_label / filename
            checklist = sanitize_checklist(checklist_payload) if has_checklist_payload else self.local.read_checklist(chart_path)
            updated = self.local.update_notes(normalized_ticker, date_label, filename, notes, checklist)
            if not updated:
                return {"error": "Chart not found."}, 404

        return {
            "message": "Notes updated.",
            "chart": {
                "ticker": normalized_ticker,
                "date": date_label,
                "filename": filename,
                "notes": notes,
                "checklist": checklist,
            },
        }, 200

    def get_chart_file_path(self, ticker: str, date_label: str, filename: str) -> Path | None:
        normalized_ticker = ticker.strip().upper()
        chart_path = self.settings.storage_dir / normalized_ticker / date_label / filename
        return chart_path if chart_path.exists() and chart_path.is_file() else None

    def find_external_chart(self, ticker: str, date_label: str, filename: str):
        normalized_ticker = ticker.strip().upper()
        return next(
            (
                c
                for c in self.external.list_all_charts()
                if c["ticker"] == normalized_ticker and c["date"] == date_label and c["filename"] == filename
            ),
            None,
        )
