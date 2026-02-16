from __future__ import annotations

import secrets
from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import uuid4

from .models import LoginSession, PipelineJob, PipelineStatus
from .repository import PipelineRepository


@dataclass(slots=True)
class BrowserContextBinding:
    context_id: str
    page_id: str


class BrowserSessionManager:
    """Best-effort managed browser contexts for login verification."""

    def __init__(self) -> None:
        self._contexts: dict[str, dict[str, object]] = {}
        self._playwright = None
        self._browser = None

    def create_context(self) -> BrowserContextBinding:
        context_id = str(uuid4())
        page_id = str(uuid4())

        context = None
        page = None
        try:
            from playwright.sync_api import sync_playwright  # type: ignore

            if self._playwright is None:
                self._playwright = sync_playwright().start()
                self._browser = self._playwright.chromium.launch(headless=False)

            context = self._browser.new_context()
            page = context.new_page()
            page_id = str(id(page))
            context_id = str(id(context))
        except Exception:
            # Playwright is optional in local test environments; we still keep
            # deterministic context ids so session binding logic is testable.
            context = None
            page = None

        self._contexts[context_id] = {"context": context, "page": page, "is_authenticated": False}
        return BrowserContextBinding(context_id=context_id, page_id=page_id)

    def open_tradingview_login(self, context_id: str, tradingview_url: str) -> bool:
        entry = self._contexts.get(context_id)
        if not entry:
            return False
        page = entry.get("page")
        if page:
            try:
                page.goto(tradingview_url, wait_until="domcontentloaded")
            except Exception:
                return False
        return True

    def has_tradingview_auth(self, context_id: str) -> bool:
        entry = self._contexts.get(context_id)
        if not entry:
            return False

        context = entry.get("context")
        if not context:
            return bool(entry.get("is_authenticated"))

        try:
            cookies = context.cookies(["https://www.tradingview.com"])  # type: ignore[attr-defined]
        except Exception:
            return False

        auth_cookie_names = {"sessionid", "tv_ecuid", "tv_signin"}
        return any(cookie.get("name") in auth_cookie_names for cookie in cookies)

    def mark_authenticated_for_testing(self, context_id: str) -> None:
        entry = self._contexts.get(context_id)
        if entry is not None:
            entry["is_authenticated"] = True


class PipelineService:
    def __init__(self, repository: PipelineRepository, browser_manager: BrowserSessionManager | None = None) -> None:
        self.repository = repository
        self.browser_manager = browser_manager or BrowserSessionManager()

    def start_job(self, host_base_url: str) -> dict:
        job_id = str(uuid4())
        session_id = str(uuid4())
        one_time_token = secrets.token_urlsafe(32)

        job = PipelineJob(job_id=job_id, status=PipelineStatus.awaiting_login, login_session_id=session_id)
        context_binding = self.browser_manager.create_context()
        job.playwright_context_id = context_binding.context_id
        job.playwright_page_id = context_binding.page_id
        self.repository.create_job(job)

        session = LoginSession(session_id=session_id, job_id=job_id, one_time_token=one_time_token)
        self.repository.create_login_session(session)

        login_url = f"{host_base_url.rstrip('/')}/api/pipeline/login/{session_id}?token={one_time_token}"

        return {
            "job_id": job_id,
            "status": job.status,
            "login_session_id": session_id,
            "playwright_context_id": job.playwright_context_id,
            "login_url": login_url,
        }

    def open_login_session(self, session_id: str, token: str) -> tuple[dict, int]:
        session = self.repository.get_login_session(session_id)
        if not session:
            return {"error": "Login session not found."}, 404
        if session.is_consumed:
            return {"error": "Login session URL already consumed."}, 410
        if token != session.one_time_token:
            return {"error": "Invalid login session token."}, 403

        job = self.repository.get_job(session.job_id)
        if not job or not job.playwright_context_id:
            return {"error": "Pipeline job not found."}, 404

        did_open = self.browser_manager.open_tradingview_login(job.playwright_context_id, job.tradingview_url)
        if not did_open:
            return {"error": "Unable to open TradingView in controlled session."}, 500

        session.is_consumed = True
        session.consumed_at = datetime.now(tz=timezone.utc).isoformat()
        self.repository.save_login_session(session)

        job.status = PipelineStatus.login_in_progress
        self.repository.save_job(job)

        return {
            "job_id": job.job_id,
            "status": job.status,
            "playwright_context_id": job.playwright_context_id,
            "message": "Controlled TradingView login window opened.",
        }, 200

    def resume_after_login(self, job_id: str) -> tuple[dict, int]:
        job = self.repository.get_job(job_id)
        if not job:
            return {"error": "Pipeline job not found."}, 404
        if not job.playwright_context_id:
            return {"error": "Playwright context not bound to job."}, 409

        is_authenticated = self.browser_manager.has_tradingview_auth(job.playwright_context_id)
        if not is_authenticated:
            return {
                "job_id": job.job_id,
                "status": job.status,
                "error": "TradingView authentication not detected in controlled browser context.",
            }, 409

        job.status = PipelineStatus.running_capture
        job.auth_verified_at = datetime.now(tz=timezone.utc).isoformat()
        self.repository.save_job(job)

        return {
            "job_id": job.job_id,
            "status": job.status,
            "auth_verified_at": job.auth_verified_at,
            "playwright_context_id": job.playwright_context_id,
        }, 200
