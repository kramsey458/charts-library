from __future__ import annotations

import os
from pathlib import Path

from flask import Blueprint, Flask, jsonify, request
from flask_cors import CORS

from .config import load_settings
from .pipeline import PipelineService, PipelineWorker
from .pipeline.repository import SQLitePipelineRepository
from .routes import create_api_blueprint
from .service import ChartService


def _ensure_pipeline_routes(app: Flask, pipeline_service: PipelineService, worker: PipelineWorker) -> None:
    existing_rules = {rule.rule for rule in app.url_map.iter_rules()}
    if "/api/pipeline/jobs" in existing_rules:
        return

    pipeline = Blueprint("pipeline_fallback", __name__)

    def owner_id() -> str:
        return request.headers.get("X-Owner-Id", "demo-user").strip() or "demo-user"

    def err(exc):
        return jsonify({"error": {"code": exc.code, "message": exc.message, "details": exc.details}}), exc.status

    @pipeline.post("/api/pipeline/jobs")
    @pipeline.post("/api/pipeline/jobs/")
    def create_pipeline_job():
        from .pipeline.service import PipelineError

        try:
            if request.content_type and request.content_type.startswith("multipart/form-data"):
                ticker_file = request.files.get("ticker_file")
                if not ticker_file:
                    raise PipelineError("MISSING_FILE", "ticker_file is required for multipart uploads.")
                filename = (ticker_file.filename or "").lower()
                if not (filename.endswith(".txt") or filename.endswith(".csv")):
                    raise PipelineError("INVALID_FILE_TYPE", "Only .txt and .csv ticker files are supported.")
                text = pipeline_service.parse_uploaded_text(ticker_file.read())
            else:
                payload = request.get_json(silent=True) or {}
                text = str(payload.get("tickers_text", ""))
            tickers, invalid_rows = pipeline_service.parse_tickers_text(text)
            job = pipeline_service.create_job(owner_id(), tickers, invalid_rows)
            return jsonify(pipeline_service.serialize_job(job)), 201
        except PipelineError as exc:
            return err(exc)

    @pipeline.post("/api/pipeline/jobs/<job_id>/start")
    def start_pipeline_job(job_id: str):
        from .pipeline.service import PipelineError

        try:
            payload = pipeline_service.start_job(job_id, owner_id())
            worker.start_job(job_id)
            return jsonify(payload)
        except PipelineError as exc:
            return err(exc)

    @pipeline.get("/api/pipeline/jobs/<job_id>")
    def get_pipeline_job(job_id: str):
        from .pipeline.service import PipelineError

        try:
            job = pipeline_service.get_job_owned(job_id, owner_id())
            return jsonify(pipeline_service.serialize_job(job))
        except PipelineError as exc:
            return err(exc)

    @pipeline.get("/api/pipeline/login/<session_id>")
    def open_pipeline_login(session_id: str):
        from .pipeline.service import PipelineError

        token = request.args.get("token", "")
        try:
            payload, status = pipeline_service.open_login_session(session_id, token, owner_id())
            return jsonify(payload), status
        except PipelineError as exc:
            return err(exc)

    @pipeline.post("/api/pipeline/jobs/<job_id>/resume-after-login")
    def resume_pipeline_after_login(job_id: str):
        from .pipeline.service import PipelineError

        try:
            payload = pipeline_service.resume_after_login(job_id, owner_id())
            worker.start_job(job_id)
            return jsonify(payload)
        except PipelineError as exc:
            return err(exc)

    @pipeline.post("/api/pipeline/jobs/<job_id>/upload-decision")
    def submit_pipeline_upload_decision(job_id: str):
        from .pipeline.service import PipelineError

        try:
            payload = pipeline_service.submit_upload_decision(job_id, owner_id(), request.get_json(silent=True) or {})
            worker.start_job(job_id)
            return jsonify(payload)
        except PipelineError as exc:
            return err(exc)

    @pipeline.post("/api/pipeline/jobs/<job_id>/cancel")
    def cancel_pipeline_job(job_id: str):
        from .pipeline.service import PipelineError

        try:
            payload = pipeline_service.cancel_job(job_id, owner_id())
            return jsonify(payload)
        except PipelineError as exc:
            return err(exc)

    app.register_blueprint(pipeline)


def create_app() -> Flask:
    app = Flask(__name__)
    CORS(app)

    settings = load_settings()
    service = ChartService(settings)

    if not settings.is_external:
        service.local.ensure_storage()

    pipeline_db_path = Path(os.environ.get("PIPELINE_DB_PATH", settings.base_dir / "pipeline" / "pipeline.sqlite3"))
    artifact_dir = Path(os.environ.get("PIPELINE_ARTIFACT_DIR", settings.base_dir / "pipeline" / "artifacts"))
    repo = SQLitePipelineRepository(pipeline_db_path)
    pipeline_service = PipelineService(repo=repo, chart_service=service, artifact_dir=artifact_dir)
    worker = PipelineWorker(pipeline_service)

    app.extensions["pipeline_service"] = pipeline_service
    app.extensions["pipeline_worker"] = worker

    app.register_blueprint(create_api_blueprint(service, pipeline_service=pipeline_service, worker=worker))
    _ensure_pipeline_routes(app, pipeline_service, worker)
    return app
