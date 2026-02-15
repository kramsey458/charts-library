from __future__ import annotations

import json
import sqlite3
from abc import ABC, abstractmethod
from dataclasses import asdict
from pathlib import Path

from .models import LoginSession, PipelineItem, PipelineJob


class PipelineRepository(ABC):
    @abstractmethod
    def save_job(self, job: PipelineJob) -> None: ...

    @abstractmethod
    def get_job(self, job_id: str) -> PipelineJob | None: ...

    @abstractmethod
    def save_session(self, session: LoginSession) -> None: ...

    @abstractmethod
    def get_session(self, session_id: str) -> LoginSession | None: ...


class SQLitePipelineRepository(PipelineRepository):
    def __init__(self, db_path: Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self):
        return sqlite3.connect(self.db_path)

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS pipeline_jobs (
                    id TEXT PRIMARY KEY,
                    owner_id TEXT NOT NULL,
                    payload TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS login_sessions (
                    id TEXT PRIMARY KEY,
                    job_id TEXT NOT NULL,
                    owner_id TEXT NOT NULL,
                    payload TEXT NOT NULL
                )
                """
            )

    def save_job(self, job: PipelineJob) -> None:
        payload = asdict(job)
        payload["items"] = [asdict(item) for item in job.items]
        with self._connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO pipeline_jobs(id, owner_id, payload) VALUES(?, ?, ?)",
                (job.id, job.owner_id, json.dumps(payload)),
            )

    def get_job(self, job_id: str) -> PipelineJob | None:
        with self._connect() as conn:
            row = conn.execute("SELECT payload FROM pipeline_jobs WHERE id = ?", (job_id,)).fetchone()
        if not row:
            return None
        payload = json.loads(row[0])
        items = [PipelineItem(**item) for item in payload.pop("items", [])]
        return PipelineJob(items=items, **payload)

    def save_session(self, session: LoginSession) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO login_sessions(id, job_id, owner_id, payload) VALUES(?, ?, ?, ?)",
                (session.id, session.job_id, session.owner_id, json.dumps(asdict(session))),
            )

    def get_session(self, session_id: str) -> LoginSession | None:
        with self._connect() as conn:
            row = conn.execute("SELECT payload FROM login_sessions WHERE id = ?", (session_id,)).fetchone()
        if not row:
            return None
        return LoginSession(**json.loads(row[0]))
