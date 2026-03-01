from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .checklist import empty_checklist, sanitize_checklist


class LocalStorage:
    def __init__(self, storage_dir: Path) -> None:
        self.storage_dir = storage_dir

    def ensure_storage(self) -> None:
        self.storage_dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def checklist_file_path(chart_file: Path) -> Path:
        return chart_file.parent / f"{chart_file.stem}.checklist.json"

    @staticmethod
    def classification_file_path(chart_file: Path) -> Path:
        return chart_file.parent / f"{chart_file.stem}.classification.json"

    @staticmethod
    def analysis_file_path(chart_file: Path) -> Path:
        return chart_file.parent / f"{chart_file.stem}.analysis.json"

    @staticmethod
    def timeframe_file_path(chart_file: Path) -> Path:
        return chart_file.parent / f"{chart_file.stem}.timeframe.txt"

    @staticmethod
    def sanitize_timeframe(timeframe: str | None) -> str:
        normalized = str(timeframe or "").strip().upper()
        if normalized not in {"D", "W", "M"}:
            return "D"
        return normalized

    @staticmethod
    def sanitize_classification(classification: dict[str, Any] | None) -> dict[str, Any]:
        payload = classification if isinstance(classification, dict) else {}

        label = payload.get("classification_label")
        if label is not None:
            label = str(label).strip() or None

        timestamp = payload.get("classification_timestamp")
        if timestamp is not None:
            timestamp = str(timestamp).strip() or None

        config_version = payload.get("classifier_config_version")
        if config_version is not None:
            config_version = str(config_version).strip() or None

        def to_int(name: str) -> int | None:
            raw = payload.get(name)
            if raw in (None, ""):
                return None
            try:
                return int(raw)
            except (TypeError, ValueError):
                return None

        return {
            "classification_label": label,
            "classification_red_pixels": to_int("classification_red_pixels"),
            "classification_yellow_pixels": to_int("classification_yellow_pixels"),
            "classifier_config_version": config_version,
            "classification_timestamp": timestamp,
        }

    @staticmethod
    def sanitize_analysis(analysis: dict[str, Any] | None) -> dict[str, Any]:
        payload = analysis if isinstance(analysis, dict) else {}
        status = str(payload.get("status") or "idle").strip().lower()
        if status not in {"idle", "running", "completed", "failed"}:
            status = "idle"

        def clean_str(name: str) -> str:
            return str(payload.get(name) or "").strip()

        return {
            "status": status,
            "model": clean_str("model"),
            "prompt_version": clean_str("prompt_version"),
            "text": clean_str("text"),
            "error": clean_str("error"),
            "started_at": clean_str("started_at"),
            "completed_at": clean_str("completed_at"),
        }

    def read_checklist(self, chart_file: Path) -> dict[str, bool]:
        metadata_path = self.checklist_file_path(chart_file)
        if not metadata_path.exists() or not metadata_path.is_file():
            return empty_checklist()

        try:
            payload = json.loads(metadata_path.read_text(encoding="utf-8"))
        except Exception:
            return empty_checklist()

        return sanitize_checklist(payload if isinstance(payload, dict) else {})

    def write_checklist(self, chart_file: Path, checklist: dict[str, bool]) -> None:
        metadata_path = self.checklist_file_path(chart_file)
        metadata_path.write_text(json.dumps(sanitize_checklist(checklist)), encoding="utf-8")

    def read_classification(self, chart_file: Path) -> dict[str, Any]:
        metadata_path = self.classification_file_path(chart_file)
        if not metadata_path.exists() or not metadata_path.is_file():
            return self.sanitize_classification({})

        try:
            payload = json.loads(metadata_path.read_text(encoding="utf-8"))
        except Exception:
            return self.sanitize_classification({})

        return self.sanitize_classification(payload if isinstance(payload, dict) else {})

    def write_classification(self, chart_file: Path, classification: dict[str, Any] | None) -> None:
        metadata_path = self.classification_file_path(chart_file)
        metadata_path.write_text(json.dumps(self.sanitize_classification(classification)), encoding="utf-8")

    def read_analysis(self, chart_file: Path) -> dict[str, Any]:
        metadata_path = self.analysis_file_path(chart_file)
        if not metadata_path.exists() or not metadata_path.is_file():
            return self.sanitize_analysis({})

        try:
            payload = json.loads(metadata_path.read_text(encoding="utf-8"))
        except Exception:
            return self.sanitize_analysis({})

        return self.sanitize_analysis(payload if isinstance(payload, dict) else {})

    def write_analysis(self, chart_file: Path, analysis: dict[str, Any] | None) -> None:
        metadata_path = self.analysis_file_path(chart_file)
        metadata_path.write_text(json.dumps(self.sanitize_analysis(analysis)), encoding="utf-8")

    def list_tickers(self) -> list[str]:
        self.ensure_storage()
        return sorted(path.name for path in self.storage_dir.iterdir() if path.is_dir())

    def list_charts_for_ticker(self, ticker: str) -> list[dict]:
        self.ensure_storage()
        ticker_dir = self.storage_dir / ticker
        if not ticker_dir.exists():
            return []

        charts: list[dict] = []
        for date_dir in sorted(ticker_dir.iterdir(), reverse=True):
            if not date_dir.is_dir():
                continue
            for chart_file in sorted(date_dir.glob("*.png")):
                notes_path = date_dir / f"{chart_file.stem}.notes.txt"
                notes = notes_path.read_text(encoding="utf-8").strip() if notes_path.exists() else ""
                charts.append(
                    {
                        "ticker": ticker,
                        "date": date_dir.name,
                        "filename": chart_file.name,
                        "url": f"/api/chart-file/{ticker}/{date_dir.name}/{chart_file.name}",
                        "notes": notes,
                        "checklist": self.read_checklist(chart_file),
                        **self.read_classification(chart_file),
                        "analysis": self.read_analysis(chart_file),
                        "timeframe": self.read_timeframe(chart_file),
                    }
                )

        return charts

    def save_chart(
        self,
        ticker: str,
        date_label: str,
        filename: str,
        notes: str,
        checklist: dict[str, bool],
        classification: dict[str, Any] | None,
        timeframe: str,
        chart_file,
    ) -> None:
        target_dir = self.storage_dir / ticker / date_label
        target_dir.mkdir(parents=True, exist_ok=True)
        target_path = target_dir / filename
        chart_file.save(target_path)

        notes_path = target_dir / f"{Path(filename).stem}.notes.txt"
        if notes:
            notes_path.write_text(notes, encoding="utf-8")
        elif notes_path.exists() and notes_path.is_file():
            notes_path.unlink()

        self.write_checklist(target_path, checklist)
        self.write_classification(target_path, classification)
        self.write_analysis(target_path, {})
        self.write_timeframe(target_path, timeframe)

    def read_timeframe(self, chart_file: Path) -> str:
        metadata_path = self.timeframe_file_path(chart_file)
        if not metadata_path.exists() or not metadata_path.is_file():
            return "D"

        return self.sanitize_timeframe(metadata_path.read_text(encoding="utf-8"))

    def write_timeframe(self, chart_file: Path, timeframe: str | None) -> None:
        metadata_path = self.timeframe_file_path(chart_file)
        metadata_path.write_text(self.sanitize_timeframe(timeframe), encoding="utf-8")

    def delete_chart(self, ticker: str, date_label: str, filename: str) -> bool:
        chart_path = self.storage_dir / ticker / date_label / filename
        if not chart_path.exists() or not chart_path.is_file():
            return False

        chart_path.unlink()
        notes_path = chart_path.parent / f"{chart_path.stem}.notes.txt"
        if notes_path.exists() and notes_path.is_file():
            notes_path.unlink()

        checklist_path = self.checklist_file_path(chart_path)
        if checklist_path.exists() and checklist_path.is_file():
            checklist_path.unlink()

        classification_path = self.classification_file_path(chart_path)
        if classification_path.exists() and classification_path.is_file():
            classification_path.unlink()

        analysis_path = self.analysis_file_path(chart_path)
        if analysis_path.exists() and analysis_path.is_file():
            analysis_path.unlink()

        timeframe_path = self.timeframe_file_path(chart_path)
        if timeframe_path.exists() and timeframe_path.is_file():
            timeframe_path.unlink()

        date_dir = chart_path.parent
        ticker_dir = date_dir.parent
        if date_dir.exists() and not any(date_dir.iterdir()):
            date_dir.rmdir()
        if ticker_dir.exists() and not any(ticker_dir.iterdir()):
            ticker_dir.rmdir()

        return True

    def update_notes(
        self,
        ticker: str,
        date_label: str,
        filename: str,
        notes: str,
        checklist: dict[str, bool],
        timeframe: str | None = None,
    ) -> bool:
        chart_path = self.storage_dir / ticker / date_label / filename
        if not chart_path.exists() or not chart_path.is_file():
            return False

        notes_path = chart_path.parent / f"{chart_path.stem}.notes.txt"
        if notes:
            notes_path.write_text(notes, encoding="utf-8")
        elif notes_path.exists() and notes_path.is_file():
            notes_path.unlink()

        self.write_checklist(chart_path, checklist)
        if timeframe is not None:
            self.write_timeframe(chart_path, timeframe)
        return True
