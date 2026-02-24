from __future__ import annotations

from flask import Blueprint, jsonify, redirect, request, send_from_directory

from .service import ChartService


def create_api_blueprint(service: ChartService) -> Blueprint:
    api = Blueprint("api", __name__)

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


    @api.post("/api/charts/<ticker>/<date_label>/<filename>/analyze")
    def analyze_chart(ticker: str, date_label: str, filename: str):
        validation_error = require_config()
        if validation_error:
            return validation_error
        try:
            payload, status = service.analyze_chart(ticker, date_label, filename)
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

    return api
