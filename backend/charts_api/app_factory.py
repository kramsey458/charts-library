from __future__ import annotations

from flask import Flask
from flask_cors import CORS

from .config import load_settings
from .pipeline import PipelineRepository, PipelineService
from .routes import create_api_blueprint
from .service import ChartService


def create_app() -> Flask:
    app = Flask(__name__)
    CORS(app)

    settings = load_settings()
    service = ChartService(settings)

    if not settings.is_external:
        service.local.ensure_storage()

    pipeline_repository = PipelineRepository()
    pipeline_service = PipelineService(repository=pipeline_repository)

    app.register_blueprint(create_api_blueprint(service, pipeline_service=pipeline_service))
    return app
