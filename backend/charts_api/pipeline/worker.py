from __future__ import annotations

import logging
import threading
import time

from .models import TERMINAL_STATES

LOGGER = logging.getLogger(__name__)


class PipelineWorker:
    def __init__(self, service) -> None:
        self.service = service
        self._threads: dict[str, threading.Thread] = {}

    def start_job(self, job_id: str) -> None:
        if job_id in self._threads and self._threads[job_id].is_alive():
            return
        thread = threading.Thread(target=self._run, args=(job_id,), daemon=True)
        self._threads[job_id] = thread
        thread.start()

    def _run(self, job_id: str) -> None:
        while True:
            job = self.service.repo.get_job(job_id)
            if not job or job.state in TERMINAL_STATES:
                return
            if job.state == "running_capture":
                LOGGER.info("pipeline capture", extra={"job_id": job_id})
                self.service.run_capture(job_id)
            elif job.state == "running_classify":
                LOGGER.info("pipeline classify", extra={"job_id": job_id})
                self.service.run_classification(job_id)
            elif job.state == "running_upload":
                LOGGER.info("pipeline upload", extra={"job_id": job_id})
                self.service.run_upload(job_id)
            time.sleep(0.2)
