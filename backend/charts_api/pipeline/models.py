from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum


def utc_now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


class PipelineStatus(str, Enum):
    awaiting_login = "awaiting_login"
    login_in_progress = "login_in_progress"
    running_capture = "running_capture"


@dataclass(slots=True)
class LoginSession:
    session_id: str
    job_id: str
    one_time_token: str
    is_consumed: bool = False
    created_at: str = field(default_factory=utc_now_iso)
    consumed_at: str | None = None


@dataclass(slots=True)
class PipelineJob:
    job_id: str
    status: PipelineStatus
    created_at: str = field(default_factory=utc_now_iso)
    updated_at: str = field(default_factory=utc_now_iso)
    tradingview_url: str = "https://www.tradingview.com/#signin"
    playwright_context_id: str | None = None
    playwright_page_id: str | None = None
    login_session_id: str | None = None
    auth_verified_at: str | None = None

    def touch(self) -> None:
        self.updated_at = utc_now_iso()
