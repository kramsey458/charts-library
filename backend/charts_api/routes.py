from __future__ import annotations

from flask import Blueprint, jsonify, request, send_from_directory

from .pipeline.service import PipelineError
from .service import ChartService


def create_api_blueprint(service: ChartService, pipeline_service=None, worker=None) -> Blueprint:
    api = Blueprint("api", __name__)

    def owner_id() -> str:
        return request.headers.get("X-Owner-Id", "demo-user").strip() or "demo-user"

    def error_envelope(exc: PipelineError):
        return jsonify({"error": {"code": exc.code, "message": exc.message, "details": exc.details}}), exc.status

    @api.get("/api/health")
    def health():
        payload = {"status": "ok", "storage_mode": service.settings.storage_mode}
        if service.is_external:
            payload["provider"] = "cloudinary"
        return jsonify(payload)

    def require_config():
        is_ok, err = service.validate_external_config()
        if is_ok:
            return None
        payload, status = err
        return jsonify(payload), status

    @api.get("/api/tickers")
    def get_tickers():
        validation_error = require_config()
        if validation_error:
            return validation_error
        try:
            tickers, chart_counts, total_charts = service.build_ticker_stats()
        except RuntimeError as exc:
            return jsonify({"error": str(exc)}), 502

        return jsonify({"tickers": tickers, "chart_counts": chart_counts, "total_charts": total_charts})

    @api.get("/api/charts/<ticker>")
    def get_charts(ticker: str):
        validation_error = require_config()
        if validation_error:
            return validation_error
        try:
            return jsonify({"charts": service.list_charts(ticker)})
        except RuntimeError as exc:
            return jsonify({"error": str(exc)}), 502

    @api.post("/api/charts")
    def upload_chart():
        validation_error = require_config()
        if validation_error:
            return validation_error
        try:
            payload, status = service.upload_chart(request.form, request.files)
            return jsonify(payload), status
        except RuntimeError as exc:
            return jsonify({"error": str(exc)}), 502

    @api.post("/api/uploads/charts")
    def upload_chart_for_processing_app():
        validation_error = require_config()
        if validation_error:
            return validation_error
        try:
            payload, status = service.upload_chart(request.form, request.files, image_field_names=("image", "chart"))
            return jsonify(payload), status
        except RuntimeError as exc:
            return jsonify({"error": str(exc)}), 502

    @api.delete("/api/charts/<ticker>/<date_label>/<filename>")
    def delete_chart(ticker: str, date_label: str, filename: str):
        validation_error = require_config()
        if validation_error:
            return validation_error
        try:
            payload, status = service.delete_chart(ticker, date_label, filename)
            return jsonify(payload), status
        except RuntimeError as exc:
            return jsonify({"error": str(exc)}), 502

    @api.patch("/api/charts/<ticker>/<date_label>/<filename>/notes")
    def update_chart_notes(ticker: str, date_label: str, filename: str):
        validation_error = require_config()
        if validation_error:
            return validation_error
        try:
            payload, status = service.update_notes(ticker, date_label, filename, request.get_json(silent=True) or {})
            return jsonify(payload), status
        except RuntimeError as exc:
            return jsonify({"error": str(exc)}), 502

    @api.get("/api/chart-file/<ticker>/<date_label>/<filename>")
    def get_chart_file(ticker: str, date_label: str, filename: str):
        validation_error = require_config()
        if validation_error:
            return validation_error

        try:
            if service.is_external:
                chart = service.find_external_chart(ticker, date_label, filename)
                if not chart or not chart.get("secure_url"):
                    return jsonify({"error": "Chart not found."}), 404
                return redirect(chart["secure_url"], code=302)

            chart_path = service.get_chart_file_path(ticker, date_label, filename)
            if not chart_path:
                return jsonify({"error": "Chart not found."}), 404
            return send_from_directory(chart_path.parent, chart_path.name)
        except RuntimeError as exc:
            return jsonify({"error": str(exc)}), 502

    @api.get("/api/classifier/config")
    def get_classifier_config():
        payload = {"config": service.get_classifier_config()}
        return jsonify(payload)

    @api.put("/api/classifier/config")
    def put_classifier_config():
        payload, status = service.update_classifier_config(request.get_json(silent=True) or {})
        return jsonify(payload), status

    @api.post("/api/classifier/preview")
    def classifier_preview():
        payload, status = service.classifier_preview(request.form, request.files)
        return jsonify(payload), status

    @api.post("/api/classifier/batch/plan")
    def classifier_batch_plan():
        payload, status = service.classifier_batch_plan(request.form, request.files)
        return jsonify(payload), status

    @api.post("/api/classifier/batch/upload")
    def classifier_batch_upload():
        validation_error = require_config()
        if validation_error:
            return validation_error
        try:
            payload, status = service.classifier_batch_upload(request.form, request.files)
            return jsonify(payload), status
        except RuntimeError as exc:
            return jsonify({"error": str(exc)}), 502

    @api.post("/api/pipeline/jobs")
    @api.post("/api/pipeline/jobs/")
    def create_pipeline_job():
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
            return error_envelope(exc)

    @api.post("/api/pipeline/jobs/<job_id>/start")
    def start_pipeline_job(job_id: str):
        try:
            payload = pipeline_service.start_job(job_id, owner_id())
            worker.start_job(job_id)
            return jsonify(payload)
        except PipelineError as exc:
            return error_envelope(exc)

    @api.get("/api/pipeline/jobs/<job_id>")
    def get_pipeline_job(job_id: str):
        try:
            job = pipeline_service.get_job_owned(job_id, owner_id())
            return jsonify(pipeline_service.serialize_job(job))
        except PipelineError as exc:
            return error_envelope(exc)

    @api.get("/api/pipeline/login/<session_id>")
    def open_pipeline_login(session_id: str):
        token = request.args.get("token", "")
        try:
            payload, status = pipeline_service.open_login_session(session_id, token, owner_id())
            return jsonify(payload), status
        except PipelineError as exc:
            return error_envelope(exc)


    @api.get("/api/pipeline/jobs/<job_id>/images.zip")
    def download_pipeline_images(job_id: str):
        try:
            job = pipeline_service.get_job_owned(job_id, owner_id())
            zip_path = pipeline_service.get_job_zip_path(job.id)
            if not zip_path:
                return jsonify({"error": {"code": "ZIP_NOT_READY", "message": "Zip archive is not ready.", "details": {}}}), 404
            return send_from_directory(zip_path.parent, zip_path.name, as_attachment=True)
        except PipelineError as exc:
            return error_envelope(exc)

    @api.post("/api/pipeline/jobs/<job_id>/resume-after-login")
    def resume_pipeline_after_login(job_id: str):
        try:
            payload = pipeline_service.resume_after_login(job_id, owner_id())
            worker.start_job(job_id)
            return jsonify(payload)
        except PipelineError as exc:
            return error_envelope(exc)

    @api.post("/api/pipeline/jobs/<job_id>/upload-decision")
    def submit_pipeline_upload_decision(job_id: str):
        try:
            payload = pipeline_service.submit_upload_decision(job_id, owner_id(), request.get_json(silent=True) or {})
            worker.start_job(job_id)
            return jsonify(payload)
        except PipelineError as exc:
            return error_envelope(exc)

    @api.post("/api/pipeline/jobs/<job_id>/cancel")
    def cancel_pipeline_job(job_id: str):
        try:
            payload = pipeline_service.cancel_job(job_id, owner_id())
            return jsonify(payload)
        except PipelineError as exc:
            return error_envelope(exc)

    return api
