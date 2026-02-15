from __future__ import annotations

import os
from pathlib import Path

from flask import Flask
from flask_cors import CORS

from .config import load_settings
from .pipeline import PipelineService, PipelineWorker
from .pipeline.repository import SQLitePipelineRepository
from .routes import create_api_blueprint
from .service import ChartService


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
    return app
