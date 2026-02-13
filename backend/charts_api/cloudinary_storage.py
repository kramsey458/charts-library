from __future__ import annotations

import datetime
import hashlib
from pathlib import Path
from typing import Any
from urllib.parse import quote, unquote

import requests
from werkzeug.utils import secure_filename

from .checklist import empty_checklist, encode_checklist_context, parse_checklist_context
from .local_storage import LocalStorage


class CloudinaryStorage:
    def __init__(self, cloud_name: str, api_key: str, api_secret: str, folder: str) -> None:
        self.cloud_name = cloud_name
        self.api_key = api_key
        self.api_secret = api_secret
        self.folder = folder

    def has_credentials(self) -> bool:
        return bool(self.cloud_name and self.api_key and self.api_secret)

    def build_context(
        self,
        *,
        ticker: str,
        date_label: str,
        filename: str,
        notes: str,
        checklist: dict[str, bool],
        classification: dict[str, Any] | None,
    ) -> str:
        safe_classification = LocalStorage.sanitize_classification(classification)
        return (
            f"ticker={ticker}|date={date_label}|filename={filename}|"
            f"notes={quote(notes)}|checklist={encode_checklist_context(checklist)}|"
            f"classification_label={quote(str(safe_classification.get('classification_label') or ''))}|"
            f"classification_red_pixels={safe_classification.get('classification_red_pixels') or ''}|"
            f"classification_yellow_pixels={safe_classification.get('classification_yellow_pixels') or ''}|"
            f"classifier_config_version={quote(str(safe_classification.get('classifier_config_version') or ''))}|"
            f"classification_timestamp={quote(str(safe_classification.get('classification_timestamp') or ''))}"
        )

    def signature(self, params: dict[str, Any]) -> str:
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
        return hashlib.sha1(f"{payload}{self.api_secret}".encode("utf-8")).hexdigest()

    def admin_get(self, path: str, params: dict[str, Any]) -> dict[str, Any]:
        url = f"https://api.cloudinary.com/v1_1/{self.cloud_name}/{path}"
        response = requests.get(url, params=params, auth=(self.api_key, self.api_secret), timeout=30)
        if response.status_code >= 400:
            if response.headers.get("content-type", "").startswith("application/json"):
                message = response.json().get("error", {}).get("message")
            else:
                message = "Cloudinary admin request failed."
            raise RuntimeError(message or "Cloudinary admin request failed.")
        return response.json()

    def list_all_charts(self) -> list[dict[str, Any]]:
        resources: list[dict[str, Any]] = []
        next_cursor = ""
        while True:
            payload = self.admin_get(
                "resources/image/upload",
                {
                    "prefix": f"{self.folder}/",
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
                    "checklist": parse_checklist_context(context.get("checklist", "")),
                    **LocalStorage.sanitize_classification(
                        {
                            "classification_label": unquote(str(context.get("classification_label", ""))),
                            "classification_red_pixels": context.get("classification_red_pixels"),
                            "classification_yellow_pixels": context.get("classification_yellow_pixels"),
                            "classifier_config_version": unquote(str(context.get("classifier_config_version", ""))),
                            "classification_timestamp": unquote(str(context.get("classification_timestamp", ""))),
                        }
                    ),
                    "public_id": resource.get("public_id", ""),
                    "secure_url": resource.get("secure_url", ""),
                    "created_at": resource.get("created_at", ""),
                }
            )

        charts.sort(key=lambda c: (c["ticker"], c["date"], c["filename"], c["created_at"]))
        return charts

    def upload_chart(
        self,
        ticker: str,
        date_label: str,
        filename: str,
        notes: str,
        checklist: dict[str, bool],
        classification: dict[str, Any] | None,
        chart_file,
    ) -> None:
        timestamp = int(datetime.datetime.now(datetime.timezone.utc).timestamp())
        folder = f"{self.folder}/{ticker}/{date_label}"
        safe_base_name = secure_filename(Path(filename).stem) or "chart"
        public_id = f"{folder}/{safe_base_name}"
        context = self.build_context(
            ticker=ticker,
            date_label=date_label,
            filename=filename,
            notes=notes,
            checklist=checklist,
            classification=classification,
        )
        signature = self.signature({"context": context, "overwrite": "true", "public_id": public_id, "timestamp": timestamp})
        chart_file.stream.seek(0)
        response = requests.post(
            f"https://api.cloudinary.com/v1_1/{self.cloud_name}/image/upload",
            data={
                "api_key": self.api_key,
                "timestamp": str(timestamp),
                "signature": signature,
                "public_id": public_id,
                "overwrite": "true",
                "context": context,
            },
            files={"file": (filename, chart_file.stream, chart_file.mimetype or "image/png")},
            timeout=60,
        )
        if response.status_code >= 400:
            if response.headers.get("content-type", "").startswith("application/json"):
                message = response.json().get("error", {}).get("message")
            else:
                message = "Cloudinary upload failed."
            raise RuntimeError(message or "Cloudinary upload failed.")

    def update_chart_notes(
        self,
        public_id: str,
        ticker: str,
        date_label: str,
        filename: str,
        notes: str,
        checklist: dict[str, bool],
        classification: dict[str, Any] | None,
    ) -> None:
        timestamp = int(datetime.datetime.now(datetime.timezone.utc).timestamp())
        context = self.build_context(
            ticker=ticker,
            date_label=date_label,
            filename=filename,
            notes=notes,
            checklist=checklist,
            classification=classification,
        )
        signature = self.signature(
            {"context": context, "public_id": public_id, "timestamp": timestamp, "type": "upload"}
        )
        response = requests.post(
            f"https://api.cloudinary.com/v1_1/{self.cloud_name}/image/explicit",
            data={
                "public_id": public_id,
                "type": "upload",
                "api_key": self.api_key,
                "timestamp": str(timestamp),
                "signature": signature,
                "context": context,
            },
            timeout=30,
        )
        if response.status_code >= 400:
            if response.headers.get("content-type", "").startswith("application/json"):
                message = response.json().get("error", {}).get("message")
            else:
                message = "Cloudinary note update failed."
            raise RuntimeError(message or "Cloudinary note update failed.")

    def delete_chart(self, public_id: str) -> None:
        timestamp = int(datetime.datetime.now(datetime.timezone.utc).timestamp())
        signature = self.signature({"public_id": public_id, "timestamp": timestamp})
        response = requests.post(
            f"https://api.cloudinary.com/v1_1/{self.cloud_name}/image/destroy",
            data={
                "public_id": public_id,
                "api_key": self.api_key,
                "timestamp": str(timestamp),
                "signature": signature,
            },
            timeout=30,
        )
        if response.status_code >= 400:
            if response.headers.get("content-type", "").startswith("application/json"):
                message = response.json().get("error", {}).get("message")
            else:
                message = "Cloudinary delete failed."
            raise RuntimeError(message or "Cloudinary delete failed.")

    @staticmethod
    def chart_payload(chart: dict[str, Any]) -> dict[str, Any]:
        return {
            "ticker": chart["ticker"],
            "date": chart["date"],
            "filename": chart["filename"],
            "url": f"/api/chart-file/{chart['ticker']}/{chart['date']}/{chart['filename']}",
            "notes": chart.get("notes", ""),
            "checklist": chart.get("checklist", empty_checklist()),
            "classification_label": chart.get("classification_label"),
            "classification_red_pixels": chart.get("classification_red_pixels"),
            "classification_yellow_pixels": chart.get("classification_yellow_pixels"),
            "classifier_config_version": chart.get("classifier_config_version"),
            "classification_timestamp": chart.get("classification_timestamp"),
        }
