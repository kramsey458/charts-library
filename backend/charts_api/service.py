from __future__ import annotations

import base64
import datetime
import json
import re
from pathlib import Path
from typing import Any

import cv2
import numpy as np
import requests
from werkzeug.utils import secure_filename

from .ai_analysis import OpenAIChartAnalyzer
from .candle_classifier import CandleClassifierConfig, classify_candle, load_classifier_config
from .checklist import CHECKLIST_KEYS, apply_checklist_verdicts, sanitize_checklist
from .cloudinary_storage import CloudinaryStorage
from .config import Settings
from .prompts import CHECKLIST_VERDICT_PROMPT, PROMPT_VERSION, SYSTEM_PROMPT, build_chart_analysis_prompt
from .local_storage import LocalStorage


class ChartService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.local = LocalStorage(settings.storage_dir)
        self.classifier_config_path = Path(__file__).with_name("classifier_config.json")
        self.external = CloudinaryStorage(
            cloud_name=settings.cloudinary_cloud_name,
            api_key=settings.cloudinary_api_key,
            api_secret=settings.cloudinary_api_secret,
            folder=settings.cloudinary_folder,
        )
        self.analyzer = OpenAIChartAnalyzer(
            api_key=settings.openai_api_key,
            model=settings.openai_model,
            timeout_seconds=settings.openai_timeout_seconds,
            organization=settings.openai_organization,
            project=settings.openai_project,
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

    def get_classifier_config(self) -> dict[str, Any]:
        return load_classifier_config(self.classifier_config_path).to_dict()

    def update_classifier_config(self, payload: dict[str, Any]) -> tuple[dict[str, Any], int]:
        if not isinstance(payload, dict):
            return {"error": "Config payload must be a JSON object."}, 400

        try:
            config = CandleClassifierConfig.from_dict(payload)
            self._validate_classifier_config(config)
        except ValueError as exc:
            return {"error": str(exc)}, 400

        self.classifier_config_path.write_text(json.dumps(config.to_dict(), indent=2) + "\n")
        return {"message": "Classifier config updated.", "config": config.to_dict()}, 200

    def classifier_preview(self, form, files) -> tuple[dict[str, Any], int]:
        chart_file = files.get("image") or files.get("chart")
        if not chart_file or chart_file.filename == "":
            return {"error": "Chart image is required."}, 400
        if not self.allowed_file(chart_file.filename):
            return {"error": "Only PNG files are supported."}, 400

        image_bytes = chart_file.read()
        if self._decode_png_bytes(image_bytes) is None:
            return {"error": "Malformed PNG image."}, 400

        try:
            cfg_payload = self._extract_override_payload(form)
            config = CandleClassifierConfig.from_dict(cfg_payload) if cfg_payload else load_classifier_config(self.classifier_config_path)
            self._validate_classifier_config(config)
        except ValueError as exc:
            return {"error": str(exc)}, 400

        result = classify_candle(image_bytes, config=config)
        decision_reason = self._decision_reason(result)

        response: dict[str, Any] = {
            "label": result["label"],
            "red_pixels": result["scores"]["red_pixels"],
            "yellow_pixels": result["scores"]["yellow_pixels"],
            "decision_reason": decision_reason,
        }

        include_overlay = str(form.get("include_overlay", "")).strip().lower() in {"1", "true", "yes"}
        if include_overlay:
            response["overlay_image_base64"] = self._render_overlay_base64(image_bytes, config)

        return response, 200

    def classifier_batch_plan(self, form, files) -> tuple[dict[str, Any], int]:
        return self._classifier_batch_process(form, files, do_upload=False)

    def classifier_batch_upload(self, form, files) -> tuple[dict[str, Any], int]:
        return self._classifier_batch_process(form, files, do_upload=True)

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

    def upload_chart(self, form, files, image_field_names: tuple[str, ...] = ("chart",)) -> tuple[dict, int]:
        if not self.is_external:
            self.local.ensure_storage()

        ticker = form.get("ticker", "").strip().upper()
        date_label = form.get("date", "").strip() or datetime.date.today().isoformat()
        notes = form.get("notes", "").strip()
        checklist = sanitize_checklist({key: form.get(key, "") for key in CHECKLIST_KEYS})
        classification = self.local.sanitize_classification(self._extract_classification_payload(form))
        analysis = self.local.sanitize_analysis({})
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

        if self.is_external:
            self.external.upload_chart(safe_ticker, safe_date, filename, notes, checklist, classification, analysis, chart_file)
        else:
            self.local.save_chart(safe_ticker, safe_date, filename, notes, checklist, classification, chart_file)

        return {
            "message": "Chart uploaded.",
            "chart": {
                "ticker": safe_ticker,
                "date": safe_date,
                "filename": filename,
                "url": f"/api/chart-file/{safe_ticker}/{safe_date}/{filename}",
                "notes": notes,
                "checklist": checklist,
                **classification,
                "analysis": analysis,
            },
        }, 201

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
            classification = self.local.sanitize_classification(chart)
            analysis = self.local.sanitize_analysis(chart.get("analysis"))
            self.external.update_chart_notes(chart["public_id"], normalized_ticker, date_label, filename, notes, checklist, classification, analysis)
        else:
            chart_path = self.settings.storage_dir / normalized_ticker / date_label / filename
            checklist = sanitize_checklist(checklist_payload) if has_checklist_payload else self.local.read_checklist(chart_path)
            classification = self.local.read_classification(chart_path)
            analysis = self.local.read_analysis(chart_path)
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
                **classification,
                "analysis": analysis,
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


    def get_chart(self, ticker: str, date_label: str, filename: str) -> dict[str, Any] | None:
        normalized_ticker = ticker.strip().upper()
        if self.is_external:
            chart = self.find_external_chart(normalized_ticker, date_label, filename)
            if not chart:
                return None
            return self.external.chart_payload(chart)

        chart_path = self.settings.storage_dir / normalized_ticker / date_label / filename
        if not chart_path.exists() or not chart_path.is_file():
            return None

        notes_path = chart_path.parent / f"{chart_path.stem}.notes.txt"
        notes = notes_path.read_text(encoding="utf-8").strip() if notes_path.exists() else ""
        return {
            "ticker": normalized_ticker,
            "date": date_label,
            "filename": filename,
            "url": f"/api/chart-file/{normalized_ticker}/{date_label}/{filename}",
            "notes": notes,
            "checklist": self.local.read_checklist(chart_path),
            **self.local.read_classification(chart_path),
            "analysis": self.local.read_analysis(chart_path),
        }

    def analyze_chart(self, ticker: str, date_label: str, filename: str) -> tuple[dict[str, Any], int]:
        if not self.analyzer.is_configured():
            return {"error": "OpenAI is not configured. Set OPENAI_API_KEY."}, 500

        normalized_ticker = ticker.strip().upper()
        now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()

        if self.is_external:
            chart = self.find_external_chart(normalized_ticker, date_label, filename)
            if not chart or not chart.get("secure_url"):
                return {"error": "Chart not found."}, 404

            image_response = requests.get(chart["secure_url"], timeout=30)
            if image_response.status_code >= 400:
                return {"error": "Could not fetch chart image for analysis."}, 502
            image_bytes = image_response.content

            notes = str(chart.get("notes", ""))
            checklist = sanitize_checklist(chart.get("checklist"))
            classification = self.local.sanitize_classification(chart)
            running_analysis = self.local.sanitize_analysis(
                {
                    "status": "running",
                    "model": self.settings.openai_model,
                    "prompt_version": PROMPT_VERSION,
                    "started_at": now_iso,
                }
            )
            self.external.update_chart_notes(
                chart["public_id"],
                normalized_ticker,
                date_label,
                filename,
                notes,
                checklist,
                classification,
                running_analysis,
            )

            try:
                result = self.analyzer.analyze_chart(
                    image_bytes,
                    prompt=build_chart_analysis_prompt(normalized_ticker, date_label, filename),
                    system_prompt=SYSTEM_PROMPT,
                )
                verdict_text = ""
                try:
                    checklist_result = self.analyzer.analyze_chart(
                        image_bytes,
                        prompt=CHECKLIST_VERDICT_PROMPT,
                        system_prompt="",
                    )
                    verdict_text = checklist_result.get("analysis_text", "")
                except RuntimeError:
                    verdict_text = ""
                checklist = apply_checklist_verdicts(checklist, verdict_text)
                analysis_text = str(result.get("analysis_text", "")).strip()
                if verdict_text.strip():
                    analysis_text = (
                        f"{analysis_text}\n\nChecklist verdicts:\n{verdict_text.strip()}"
                        if analysis_text
                        else verdict_text.strip()
                    )
                completed = self.local.sanitize_analysis(
                    {
                        "status": "completed",
                        "model": result.get("analysis_model", self.settings.openai_model),
                        "prompt_version": PROMPT_VERSION,
                        "text": analysis_text,
                        "started_at": now_iso,
                        "completed_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                    }
                )
            except RuntimeError as exc:
                completed = self.local.sanitize_analysis(
                    {
                        "status": "failed",
                        "model": self.settings.openai_model,
                        "prompt_version": PROMPT_VERSION,
                        "error": str(exc),
                        "started_at": now_iso,
                        "completed_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                    }
                )

            self.external.update_chart_notes(
                chart["public_id"],
                normalized_ticker,
                date_label,
                filename,
                notes,
                checklist,
                classification,
                completed,
            )
            refreshed = self.find_external_chart(normalized_ticker, date_label, filename)
            return {"chart": self.external.chart_payload(refreshed) if refreshed else None}, 200

        chart_path = self.settings.storage_dir / normalized_ticker / date_label / filename
        if not chart_path.exists() or not chart_path.is_file():
            return {"error": "Chart not found."}, 404

        image_bytes = chart_path.read_bytes()
        running_analysis = self.local.sanitize_analysis(
            {
                "status": "running",
                "model": self.settings.openai_model,
                "prompt_version": PROMPT_VERSION,
                "started_at": now_iso,
            }
        )
        self.local.write_analysis(chart_path, running_analysis)

        try:
            result = self.analyzer.analyze_chart(
                image_bytes,
                prompt=build_chart_analysis_prompt(normalized_ticker, date_label, filename),
                system_prompt=SYSTEM_PROMPT,
            )
            verdict_text = ""
            try:
                checklist_result = self.analyzer.analyze_chart(
                    image_bytes,
                    prompt=CHECKLIST_VERDICT_PROMPT,
                    system_prompt="",
                )
                verdict_text = checklist_result.get("analysis_text", "")
            except RuntimeError:
                verdict_text = ""
            checklist = self.local.read_checklist(chart_path)
            checklist = apply_checklist_verdicts(checklist, verdict_text)
            self.local.write_checklist(chart_path, checklist)
            analysis_text = str(result.get("analysis_text", "")).strip()
            if verdict_text.strip():
                analysis_text = (
                        f"{analysis_text}\n\nChecklist verdicts:\n{verdict_text.strip()}"
                        if analysis_text
                        else verdict_text.strip()
                    )
            final_analysis = self.local.sanitize_analysis(
                {
                    "status": "completed",
                    "model": result.get("analysis_model", self.settings.openai_model),
                    "prompt_version": PROMPT_VERSION,
                    "text": analysis_text,
                    "started_at": now_iso,
                    "completed_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                }
            )
        except RuntimeError as exc:
            final_analysis = self.local.sanitize_analysis(
                {
                    "status": "failed",
                    "model": self.settings.openai_model,
                    "prompt_version": PROMPT_VERSION,
                    "error": str(exc),
                    "started_at": now_iso,
                    "completed_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                }
            )

        self.local.write_analysis(chart_path, final_analysis)
        chart = self.get_chart(normalized_ticker, date_label, filename)
        return {"chart": chart}, 200

    def _extract_classification_payload(self, form) -> dict[str, Any]:
        payload = {
            "classification_label": form.get("classification_label"),
            "classification_red_pixels": form.get("classification_red_pixels"),
            "classification_yellow_pixels": form.get("classification_yellow_pixels"),
            "classifier_config_version": form.get("classifier_config_version"),
            "classification_timestamp": form.get("classification_timestamp"),
        }

        has_embedded_payload = any(value not in (None, "") for value in payload.values())
        raw_payload = form.get("classification")
        if not raw_payload:
            return payload if has_embedded_payload else {}

        try:
            parsed = json.loads(raw_payload)
        except json.JSONDecodeError:
            return payload if has_embedded_payload else {}

        if not isinstance(parsed, dict):
            return payload if has_embedded_payload else {}

        parsed_payload = {
            "classification_label": parsed.get("classification_label"),
            "classification_red_pixels": parsed.get("classification_red_pixels"),
            "classification_yellow_pixels": parsed.get("classification_yellow_pixels"),
            "classifier_config_version": parsed.get("classifier_config_version"),
            "classification_timestamp": parsed.get("classification_timestamp"),
        }

        for key, value in payload.items():
            if value not in (None, ""):
                parsed_payload[key] = value

        return parsed_payload

    def _extract_override_payload(self, form) -> dict[str, Any]:
        config_field = form.get("config")
        if not config_field:
            return {}
        try:
            parsed = json.loads(config_field)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid config JSON: {exc.msg}") from exc
        if not isinstance(parsed, dict):
            raise ValueError("Config override must be a JSON object.")
        return parsed

    def _validate_classifier_config(self, cfg: CandleClassifierConfig) -> None:
        if cfg.roi.x < 0 or cfg.roi.y < 0 or cfg.roi.width <= 0 or cfg.roi.height <= 0:
            raise ValueError("ROI bounds must have x/y >= 0 and width/height > 0.")
        if cfg.min_pixels < 0:
            raise ValueError("min_pixels must be >= 0.")
        if cfg.dominance_ratio <= 0:
            raise ValueError("dominance_ratio must be > 0.")

        for name, hsv_range in {
            "red_range_1": cfg.red_range_1,
            "red_range_2": cfg.red_range_2,
            "yellow_range": cfg.yellow_range,
        }.items():
            self._validate_hsv_triplet(f"{name}.lower", hsv_range.lower)
            self._validate_hsv_triplet(f"{name}.upper", hsv_range.upper)
            if any(lower > upper for lower, upper in zip(hsv_range.lower, hsv_range.upper, strict=True)):
                raise ValueError(f"{name} lower bounds must be <= upper bounds.")

    def _validate_hsv_triplet(self, field_name: str, values: tuple[int, int, int]) -> None:
        if len(values) != 3:
            raise ValueError(f"{field_name} must contain exactly 3 integers.")
        h, s, v = values
        if not (0 <= int(h) <= 180 and 0 <= int(s) <= 255 and 0 <= int(v) <= 255):
            raise ValueError(f"{field_name} values must be within HSV ranges: H 0-180, S/V 0-255.")

    def _decode_png_bytes(self, image_bytes: bytes) -> np.ndarray | None:
        arr = np.frombuffer(image_bytes, dtype=np.uint8)
        if arr.size == 0:
            return None
        return cv2.imdecode(arr, cv2.IMREAD_COLOR)

    def _render_overlay_base64(self, image_bytes: bytes, config: CandleClassifierConfig) -> str:
        image = self._decode_png_bytes(image_bytes)
        if image is None:
            return ""
        x, y, width, height = config.roi.x, config.roi.y, config.roi.width, config.roi.height
        end_x = min(image.shape[1], x + width)
        end_y = min(image.shape[0], y + height)
        cv2.rectangle(image, (x, y), (end_x, end_y), (255, 0, 255), 2)
        ok, encoded = cv2.imencode(".png", image)
        if not ok:
            return ""
        return base64.b64encode(encoded.tobytes()).decode("ascii")

    def _decision_reason(self, classify_result: dict[str, Any]) -> str:
        label = classify_result["label"]
        red = classify_result["scores"]["red_pixels"]
        yellow = classify_result["scores"]["yellow_pixels"]
        if label == "red":
            return f"Red dominant ({red} vs {yellow})."
        if label == "yellow":
            return f"Yellow dominant ({yellow} vs {red})."
        return f"No dominant color ({red} red, {yellow} yellow)."

    def _parse_metadata(self, filename: str, fallback_ticker: str, fallback_date: str) -> dict[str, str]:
        stem = Path(filename).stem
        match = re.search(r"(?P<ticker>[A-Za-z]{1,10})[_-](?P<date>\d{4}-\d{2}-\d{2}|\d{8})", stem)
        if not match:
            return {"ticker": fallback_ticker, "date": fallback_date}

        ticker = match.group("ticker").upper()
        date_raw = match.group("date")
        parsed_date = date_raw
        if len(date_raw) == 8 and "-" not in date_raw:
            parsed_date = f"{date_raw[:4]}-{date_raw[4:6]}-{date_raw[6:8]}"
        return {"ticker": ticker, "date": parsed_date}

    def _classifier_batch_process(self, form, files, *, do_upload: bool) -> tuple[dict[str, Any], int]:
        incoming = files.getlist("charts") or files.getlist("files")
        if not incoming:
            return {"error": "At least one chart image is required."}, 400

        decisions = {"red": "reject", "yellow": "accept", "none": "skip"}
        metadata_default_ticker = form.get("ticker", "").strip().upper()
        metadata_default_date = form.get("date", "").strip() or datetime.date.today().isoformat()

        try:
            cfg_payload = self._extract_override_payload(form)
            config = CandleClassifierConfig.from_dict(cfg_payload) if cfg_payload else load_classifier_config(self.classifier_config_path)
            self._validate_classifier_config(config)
        except ValueError as exc:
            return {"error": str(exc)}, 400

        results: list[dict[str, Any]] = []
        for chart_file in incoming:
            if not chart_file or not chart_file.filename:
                results.append({"filename": "", "error": "Missing filename."})
                continue
            if not self.allowed_file(chart_file.filename):
                results.append({"filename": chart_file.filename, "error": "Only PNG files are supported."})
                continue

            image_bytes = chart_file.read()
            if self._decode_png_bytes(image_bytes) is None:
                results.append({"filename": chart_file.filename, "error": "Malformed PNG image."})
                continue

            classify_result = classify_candle(image_bytes, config=config)
            label = classify_result["label"]
            decision = decisions[label]
            meta = self._parse_metadata(chart_file.filename, metadata_default_ticker, metadata_default_date)
            per_file: dict[str, Any] = {
                "filename": secure_filename(chart_file.filename),
                "label": label,
                "red_pixels": classify_result["scores"]["red_pixels"],
                "yellow_pixels": classify_result["scores"]["yellow_pixels"],
                "decision_reason": self._decision_reason(classify_result),
                "decision": decision,
                "ticker": meta["ticker"],
                "date": meta["date"],
            }

            if do_upload and decision == "accept":
                upload_form = {
                    "ticker": meta["ticker"],
                    "date": meta["date"],
                    "notes": "Auto-uploaded by classifier",
                    "classification_label": label,
                    "classification_red_pixels": classify_result["scores"]["red_pixels"],
                    "classification_yellow_pixels": classify_result["scores"]["yellow_pixels"],
                    "classifier_config_version": "batch-default",
                    "classification_timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                }
                chart_file.stream.seek(0)
                payload, status = self.upload_chart(upload_form, {"chart": chart_file})
                per_file["upload_result"] = {"status": status, "payload": payload}
            elif do_upload:
                per_file["upload_result"] = {"status": 200, "payload": {"message": "Skipped upload by decision."}}

            results.append(per_file)

        return {"results": results}, 200
