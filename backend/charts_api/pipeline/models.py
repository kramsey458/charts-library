from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


JOB_STATES = {
    "draft",
    "ready",
    "awaiting_login",
    "running_capture",
    "running_classify",
    "awaiting_upload_decision",
    "running_upload",
    "completed",
    "failed",
    "cancelled",
}
TERMINAL_STATES = {"completed", "failed", "cancelled"}


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class PipelineItem:
    ticker: str
    status: str = "pending"
    capture_path: str = ""
    label: str = ""
    scores: dict[str, float] = field(default_factory=dict)
    recommendation: str = "skip"
    upload_decision: str = "pending"
    upload_status: str = "pending"
    upload_payload: dict[str, Any] = field(default_factory=dict)
    errors: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class PipelineJob:
    id: str
    owner_id: str
    state: str
    created_at: str
    updated_at: str
    tickers: list[str]
    invalid_rows: list[dict[str, Any]] = field(default_factory=list)
    items: list[PipelineItem] = field(default_factory=list)
    progress: dict[str, int] = field(default_factory=dict)
    error_history: list[dict[str, Any]] = field(default_factory=list)
    upload_policy: dict[str, bool] = field(default_factory=lambda: {"upload_red": True, "upload_yellow": True, "skip_none": True})
    overrides: dict[str, str] = field(default_factory=dict)
    login_session_id: str = ""
    started_at: str = ""
    completed_at: str = ""


@dataclass
class LoginSession:
    id: str
    job_id: str
    owner_id: str
    token_hash: str
    created_at: str
    expires_at: str
    status: str = "pending"
    used_at: str = ""
    authenticated_at: str = ""
