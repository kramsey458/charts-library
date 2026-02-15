from __future__ import annotations

import hashlib
import os
import re
import secrets
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from ..candle_classifier import classify_candle
from .models import JOB_STATES, LoginSession, PipelineItem, PipelineJob, utcnow_iso
from .repository import PipelineRepository
from .tradingview_runner import run_capture

_TICKER_RE = re.compile(r"^[A-Z][A-Z0-9.\-]{0,9}$")


class PipelineError(Exception):
    def __init__(self, code: str, message: str, details: dict[str, Any] | None = None, status: int = 400):
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}
        self.status = status


class PipelineService:
    def __init__(self, repo: PipelineRepository, chart_service, artifact_dir: Path) -> None:
        self.repo = repo
        self.chart_service = chart_service
        self.artifact_dir = Path(artifact_dir)
        self.max_tickers = 200
        self.login_ttl_seconds = 600

    def parse_tickers_text(self, text: str) -> tuple[list[str], list[dict[str, Any]]]:
        valid: list[str] = []
        invalid: list[dict[str, Any]] = []
        seen: set[str] = set()
        for idx, line in enumerate(text.splitlines(), start=1):
            raw = line.strip()
            if not raw or raw.startswith("#"):
                continue
            ticker = raw.upper()
            if not _TICKER_RE.match(ticker):
                invalid.append({"line": idx, "value": raw, "reason": "Invalid symbol format"})
                continue
            if ticker not in seen:
                valid.append(ticker)
                seen.add(ticker)
        return valid, invalid

    def create_job(self, owner_id: str, tickers: list[str], invalid_rows: list[dict[str, Any]]) -> PipelineJob:
        if not tickers:
            raise PipelineError("NO_VALID_TICKERS", "No valid ticker symbols found.")
        if len(tickers) > self.max_tickers:
            raise PipelineError("TOO_MANY_TICKERS", "Ticker limit exceeded.", {"max_tickers": self.max_tickers})
        now = utcnow_iso()
        items = [PipelineItem(ticker=ticker) for ticker in tickers]
        job = PipelineJob(
            id=str(uuid4()),
            owner_id=owner_id,
            state="draft",
            created_at=now,
            updated_at=now,
            tickers=tickers,
            invalid_rows=invalid_rows,
            items=items,
            progress={"total": len(tickers), "captured": 0, "classified": 0, "approved": 0, "uploaded": 0, "failed": 0},
        )
        self.repo.save_job(job)
        return job

    def get_job_owned(self, job_id: str, owner_id: str) -> PipelineJob:
        job = self.repo.get_job(job_id)
        if not job:
            raise PipelineError("JOB_NOT_FOUND", "Pipeline job was not found.", status=404)
        if job.owner_id != owner_id:
            raise PipelineError("FORBIDDEN", "You do not own this job.", status=403)
        return job

    def start_job(self, job_id: str, owner_id: str) -> dict[str, Any]:
        job = self.get_job_owned(job_id, owner_id)
        if job.state in {"awaiting_login", "running_capture", "running_classify", "awaiting_upload_decision", "running_upload", "completed"}:
            return self.serialize_job(job)
        if job.state not in {"draft", "ready"}:
            raise PipelineError("INVALID_STATE", "Job cannot be started from current state.", {"state": job.state})
        token = secrets.token_urlsafe(24)
        token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
        now = datetime.now(timezone.utc)
        session = LoginSession(
            id=str(uuid4()),
            job_id=job.id,
            owner_id=owner_id,
            token_hash=token_hash,
            created_at=now.isoformat(),
            expires_at=(now + timedelta(seconds=self.login_ttl_seconds)).isoformat(),
        )
        self.repo.save_session(session)
        job.login_session_id = session.id
        job.state = "awaiting_login"
        job.started_at = utcnow_iso()
        job.updated_at = utcnow_iso()
        self.repo.save_job(job)
        payload = self.serialize_job(job)
        payload["launch_url"] = f"/api/pipeline/login/{session.id}?token={token}"
        payload["expires_at"] = session.expires_at
        return payload

    def open_login_session(self, session_id: str, token: str, owner_id: str) -> tuple[dict[str, Any], int]:
        session = self.repo.get_session(session_id)
        if not session:
            raise PipelineError("SESSION_NOT_FOUND", "Login session was not found.", status=404)
        if session.owner_id != owner_id:
            raise PipelineError("FORBIDDEN", "Invalid login session owner.", status=403)
        if session.status not in {"pending", "authenticated"}:
            raise PipelineError("SESSION_USED", "Login session already consumed.")
        if datetime.now(timezone.utc) > datetime.fromisoformat(session.expires_at):
            raise PipelineError("SESSION_EXPIRED", "Login session expired.")
        if hashlib.sha256(token.encode("utf-8")).hexdigest() != session.token_hash:
            raise PipelineError("INVALID_TOKEN", "Login launch token is invalid.", status=403)
        session.status = "authenticated"
        session.authenticated_at = utcnow_iso()
        self.repo.save_session(session)
        return {"message": "Login confirmed."}, 200

    def resume_after_login(self, job_id: str, owner_id: str) -> dict[str, Any]:
        job = self.get_job_owned(job_id, owner_id)
        if job.state in {"running_capture", "running_classify", "running_upload", "awaiting_upload_decision", "completed"}:
            return self.serialize_job(job)
        if job.state != "awaiting_login":
            raise PipelineError("INVALID_STATE", "Job is not waiting for login.", {"state": job.state})
        session = self.repo.get_session(job.login_session_id)
        if not session:
            raise PipelineError("SESSION_NOT_FOUND", "Login session not found.", status=404)
        if datetime.now(timezone.utc) > datetime.fromisoformat(session.expires_at):
            raise PipelineError("SESSION_EXPIRED", "Session expired. Start again to regenerate.")
        if session.status != "authenticated":
            raise PipelineError("LOGIN_NOT_CONFIRMED", "Login has not been confirmed.")
        if session.used_at:
            return self.serialize_job(job)
        session.used_at = utcnow_iso()
        session.status = "consumed"
        self.repo.save_session(session)
        job.state = "running_capture"
        job.updated_at = utcnow_iso()
        self.repo.save_job(job)
        return self.serialize_job(job)

    def submit_upload_decision(self, job_id: str, owner_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        job = self.get_job_owned(job_id, owner_id)
        if job.state in {"running_upload", "completed"}:
            return self.serialize_job(job)
        if job.state != "awaiting_upload_decision":
            raise PipelineError("INVALID_STATE", "Upload decision is not allowed now.", {"state": job.state})
        policy = payload.get("policy") or {}
        overrides = payload.get("overrides") or {}
        job.upload_policy = {
            "upload_red": bool(policy.get("upload_red", True)),
            "upload_yellow": bool(policy.get("upload_yellow", True)),
            "skip_none": bool(policy.get("skip_none", True)),
        }
        job.overrides = {str(k).upper(): str(v) for k, v in overrides.items()}
        approved = 0
        for item in job.items:
            decision = job.overrides.get(item.ticker, item.recommendation)
            item.upload_decision = decision
            if decision == "upload":
                approved += 1
        job.progress["approved"] = approved
        job.state = "running_upload"
        job.updated_at = utcnow_iso()
        self.repo.save_job(job)
        return self.serialize_job(job)

    def cancel_job(self, job_id: str, owner_id: str) -> dict[str, Any]:
        job = self.get_job_owned(job_id, owner_id)
        if job.state in {"completed", "failed", "cancelled"}:
            return self.serialize_job(job)
        job.state = "cancelled"
        job.updated_at = utcnow_iso()
        self.repo.save_job(job)
        return self.serialize_job(job)

    def run_capture(self, job_id: str) -> None:
        job = self.repo.get_job(job_id)
        if not job or job.state != "running_capture":
            return
        out_dir = self.artifact_dir / job.id
        results = run_capture(
            job.tickers,
            out_dir,
            os.environ.get("TRADINGVIEW_CHART_URL", "https://www.tradingview.com/chart/"),
            run_options={
                "mock_mode": os.environ.get("PIPELINE_CAPTURE_MOCK", "false").strip().lower() == "true",
                "headless": os.environ.get("PIPELINE_CAPTURE_HEADLESS", "false").strip().lower() == "true",
                "download_timeout_ms": int(os.environ.get("PIPELINE_CAPTURE_DOWNLOAD_TIMEOUT_MS", "20000")),
            },
        )
        if results.get("fatal_error"):
            job.error_history.append({"stage": "capture", "error": results["fatal_error"]})
        for result in results["results"]:
            item = next(i for i in job.items if i.ticker == result["ticker"])
            if result["success"]:
                item.capture_path = result["file_path"]
                item.status = "captured"
                if result.get("error"):
                    item.errors.append({"stage": "capture", "error": result["error"]})
                job.progress["captured"] += 1
            else:
                item.status = "capture_failed"
                item.errors.append({"stage": "capture", "error": result["error"]})
                job.progress["failed"] += 1
        job.state = "running_classify"
        job.updated_at = utcnow_iso()
        self.repo.save_job(job)

    def run_classification(self, job_id: str) -> None:
        job = self.repo.get_job(job_id)
        if not job or job.state != "running_classify":
            return
        for item in job.items:
            if item.status != "captured" or not item.capture_path:
                continue
            try:
                result = classify_candle(Path(item.capture_path))
                item.label = result["label"]
                item.scores = result["scores"]
                item.recommendation = "upload" if result["label"] in {"red", "yellow"} else "skip"
                item.status = "classified"
                job.progress["classified"] += 1
            except Exception as exc:
                item.status = "classify_failed"
                item.errors.append({"stage": "classify", "error": str(exc)})
                job.progress["failed"] += 1
        job.state = "awaiting_upload_decision"
        job.updated_at = utcnow_iso()
        self.repo.save_job(job)

    def run_upload(self, job_id: str) -> None:
        job = self.repo.get_job(job_id)
        if not job or job.state != "running_upload":
            return
        for item in job.items:
            if item.upload_decision != "upload" or not item.capture_path:
                if item.upload_decision != "upload":
                    item.upload_status = "skipped"
                continue
            try:
                payload, _ = self.chart_service.upload_chart_from_path(item.ticker, Path(item.capture_path), notes=f"pipeline:{job.id}")
                item.upload_status = "uploaded"
                item.upload_payload = payload
                job.progress["uploaded"] += 1
            except Exception as exc:
                item.upload_status = "failed"
                item.errors.append({"stage": "upload", "error": str(exc)})
                job.progress["failed"] += 1
        job.state = "completed" if job.progress["failed"] == 0 else "failed"
        job.completed_at = utcnow_iso()
        job.updated_at = utcnow_iso()
        self.repo.save_job(job)

    def build_upload_review(self, job: PipelineJob) -> dict[str, Any]:
        summary: dict[str, int] = {}
        for item in job.items:
            summary[item.label or "unclassified"] = summary.get(item.label or "unclassified", 0) + 1
        return {
            "summary_by_label": summary,
            "default_policy": {"upload_red": True, "upload_yellow": True, "skip_none": True},
            "recommendations": {item.ticker: item.recommendation for item in job.items},
        }

    def serialize_job(self, job: PipelineJob) -> dict[str, Any]:
        payload = {
            "id": job.id,
            "owner_id": job.owner_id,
            "state": job.state,
            "created_at": job.created_at,
            "updated_at": job.updated_at,
            "tickers": job.tickers,
            "invalid_rows": job.invalid_rows,
            "progress": job.progress,
            "items": [item.__dict__ for item in job.items],
            "error_history": job.error_history,
            "upload_review": self.build_upload_review(job) if job.state == "awaiting_upload_decision" else {},
            "completed_at": job.completed_at,
        }
        return payload

    def parse_uploaded_text(self, raw_bytes: bytes) -> str:
        try:
            return raw_bytes.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise PipelineError("INVALID_ENCODING", "Ticker file must be UTF-8.", {"error": str(exc)}) from exc
