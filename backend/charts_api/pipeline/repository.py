from __future__ import annotations

from threading import Lock

from .models import LoginSession, PipelineJob


class PipelineRepository:
    """In-memory repository for login/capture pipeline state."""

    def __init__(self) -> None:
        self._jobs: dict[str, PipelineJob] = {}
        self._login_sessions: dict[str, LoginSession] = {}
        self._lock = Lock()

    def create_job(self, job: PipelineJob) -> PipelineJob:
        with self._lock:
            self._jobs[job.job_id] = job
            return job

    def get_job(self, job_id: str) -> PipelineJob | None:
        return self._jobs.get(job_id)

    def save_job(self, job: PipelineJob) -> PipelineJob:
        with self._lock:
            job.touch()
            self._jobs[job.job_id] = job
            return job

    def create_login_session(self, session: LoginSession) -> LoginSession:
        with self._lock:
            self._login_sessions[session.session_id] = session
            return session

    def get_login_session(self, session_id: str) -> LoginSession | None:
        return self._login_sessions.get(session_id)

    def save_login_session(self, session: LoginSession) -> LoginSession:
        with self._lock:
            self._login_sessions[session.session_id] = session
            return session

    def bind_context(self, job_id: str, playwright_context_id: str, playwright_page_id: str) -> PipelineJob | None:
        with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                return None
            job.playwright_context_id = playwright_context_id
            job.playwright_page_id = playwright_page_id
            job.touch()
            self._jobs[job.job_id] = job
            return job
