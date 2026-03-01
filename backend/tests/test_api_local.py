from __future__ import annotations

import io


def upload_chart(
    client, fileobj, filename, ticker="VG", date="2026-02-11", notes="Base case", classification=None, timeframe="D"
):
    data = {
        "ticker": ticker,
        "date": date,
        "notes": notes,
        "red_candle": "true",
        "yellow_candle": "true",
        "trend_bullish": "false",
        "trend_bearish": "true",
        "macd_minus_cross": "true",
        "timeframe": timeframe,
        "chart": (fileobj, filename),
    }
    if classification:
        data.update(classification)

    return client.post(
        "/api/charts",
        data=data,
        content_type="multipart/form-data",
    )


def test_health_and_empty_tickers(client):
    health = client.get("/api/health")
    assert health.status_code == 200
    assert health.get_json()["storage_mode"] == "local"

    tickers = client.get("/api/tickers")
    assert tickers.status_code == 200
    assert tickers.get_json()["tickers"] == []


def test_upload_list_patch_and_delete_flow(client, png_file):
    fileobj, filename = png_file
    response = upload_chart(client, fileobj, filename, ticker="VG", notes="Initial VG note")
    assert response.status_code == 201

    uploaded = response.get_json()["chart"]
    assert uploaded["ticker"] == "VG"
    assert uploaded["filename"] == filename
    assert uploaded["checklist"]["red_candle"] is True
    assert uploaded["checklist"]["yellow_candle"] is True
    assert uploaded["checklist"]["trend_bearish"] is True
    assert uploaded["checklist"]["macd_minus_cross"] is True
    assert uploaded["classification_label"] is None
    assert uploaded["timeframe"] == "D"

    tickers = client.get("/api/tickers").get_json()
    assert tickers["tickers"] == ["VG"]
    assert tickers["chart_counts"]["VG"] == 1

    charts = client.get("/api/charts/VG")
    assert charts.status_code == 200
    chart = charts.get_json()["charts"][0]
    assert chart["notes"] == "Initial VG note"
    assert chart["timeframe"] == "D"

    patch = client.patch(
        f"/api/charts/VG/{chart['date']}/{chart['filename']}/notes",
        json={"notes": "Updated VG note", "checklist": {"trend_bullish": True, "macd_positive": True}, "timeframe": "W"},
    )
    assert patch.status_code == 200
    patched_chart = patch.get_json()["chart"]
    assert patched_chart["notes"] == "Updated VG note"
    assert patched_chart["checklist"]["trend_bullish"] is True
    assert patched_chart["checklist"]["macd_positive"] is True
    assert patched_chart["timeframe"] == "W"

    file_response = client.get(f"/api/chart-file/VG/{chart['date']}/{chart['filename']}")
    assert file_response.status_code == 200
    assert file_response.data.startswith(b"\x89PNG")

    delete_response = client.delete(f"/api/charts/VG/{chart['date']}/{chart['filename']}")
    assert delete_response.status_code == 200

    missing = client.get("/api/charts/VG")
    assert missing.get_json()["charts"] == []


def test_upload_validation_errors(client):
    missing_ticker = client.post(
        "/api/charts",
        data={"ticker": "", "chart": (io.BytesIO(b"fake"), "vg.png")},
        content_type="multipart/form-data",
    )
    assert missing_ticker.status_code == 400

    missing_chart = client.post(
        "/api/charts",
        data={"ticker": "VG"},
        content_type="multipart/form-data",
    )
    assert missing_chart.status_code == 400

    bad_extension = client.post(
        "/api/charts",
        data={"ticker": "VG", "chart": (io.BytesIO(b"fake"), "vg.jpg")},
        content_type="multipart/form-data",
    )
    assert bad_extension.status_code == 400


def test_rest_upload_endpoint_accepts_image_field(client, png_file):
    fileobj, filename = png_file
    response = client.post(
        "/api/uploads/charts",
        data={
            "ticker": "AAPL",
            "date": "2026-02-12",
            "notes": "Uploaded by processing app",
            "image": (fileobj, filename),
        },
        content_type="multipart/form-data",
    )

    assert response.status_code == 201
    chart = response.get_json()["chart"]
    assert chart["ticker"] == "AAPL"
    assert chart["filename"] == filename
    assert chart["timeframe"] == "D"

    charts_response = client.get("/api/charts/AAPL")
    assert charts_response.status_code == 200
    assert len(charts_response.get_json()["charts"]) == 1


def test_rest_upload_endpoint_requires_an_image_file(client):
    response = client.post(
        "/api/uploads/charts",
        data={"ticker": "AAPL", "date": "2026-02-12"},
        content_type="multipart/form-data",
    )

    assert response.status_code == 400
    assert response.get_json()["error"] == "Chart image is required."


def test_upload_persists_and_lists_classification_metadata(client, png_file):
    fileobj, filename = png_file
    classification = {
        "classification_label": "yellow",
        "classification_red_pixels": "11",
        "classification_yellow_pixels": "37",
        "classifier_config_version": "v2026.02.13",
        "classification_timestamp": "2026-02-13T12:34:56Z",
    }

    response = upload_chart(client, fileobj, filename, ticker="NVDA", classification=classification, timeframe="M")
    assert response.status_code == 201

    uploaded = response.get_json()["chart"]
    assert uploaded["classification_label"] == "yellow"
    assert uploaded["classification_red_pixels"] == 11
    assert uploaded["classification_yellow_pixels"] == 37
    assert uploaded["classifier_config_version"] == "v2026.02.13"
    assert uploaded["classification_timestamp"] == "2026-02-13T12:34:56Z"
    assert uploaded["timeframe"] == "M"

    charts = client.get("/api/charts/NVDA")
    assert charts.status_code == 200
    listed = charts.get_json()["charts"][0]
    assert listed["classification_label"] == "yellow"
    assert listed["classification_red_pixels"] == 11
    assert listed["classification_yellow_pixels"] == 37
    assert listed["classifier_config_version"] == "v2026.02.13"
    assert listed["classification_timestamp"] == "2026-02-13T12:34:56Z"
    assert listed["timeframe"] == "M"

    patch = client.patch(
        f"/api/charts/NVDA/{listed['date']}/{listed['filename']}/notes",
        json={"notes": "preserve classifier metadata"},
    )
    assert patch.status_code == 200
    patched = patch.get_json()["chart"]
    assert patched["classification_label"] == "yellow"
    assert patched["classification_red_pixels"] == 11
    assert patched["classification_yellow_pixels"] == 37
    assert patched["classifier_config_version"] == "v2026.02.13"
    assert patched["classification_timestamp"] == "2026-02-13T12:34:56Z"



def test_analyze_chart_persists_analysis(client, png_file, monkeypatch):
    fileobj, filename = png_file
    response = upload_chart(client, fileobj, filename, ticker="TSLA", notes="Ready for analysis")
    assert response.status_code == 201

    def fake_analyze(self, image_bytes, prompt, system_prompt=""):
        assert image_bytes.startswith(b"\x89PNG")
        if "Analyze this trading chart image" in prompt:
            assert "TSLA" in prompt
            return {"analysis_text": "Trend is consolidating.", "analysis_model": "gpt-5.2"}
        return {
            "analysis_text": "yellow candle\ntrend bearish\nWhale +\nMACD -\nMACD - cross",
            "analysis_model": "gpt-5.2",
        }

    monkeypatch.setattr("charts_api.ai_analysis.OpenAIChartAnalyzer.analyze_chart", fake_analyze)

    analyze = client.post(f"/api/charts/TSLA/2026-02-11/{filename}/analyze")
    assert analyze.status_code == 200

    chart = analyze.get_json()["chart"]
    assert chart["analysis"]["status"] == "completed"
    assert "Trend is consolidating." in chart["analysis"]["text"]
    assert "Checklist verdicts:" in chart["analysis"]["text"]
    assert chart["analysis"]["model"] == "gpt-5.2"
    assert chart["analysis"]["prompt_version"] == "chart-analysis-v2"
    assert chart["checklist"]["yellow_candle"] is True
    assert chart["checklist"]["trend_bearish"] is True
    assert chart["checklist"]["whale_accumulation_plus"] is True
    assert chart["checklist"]["macd_negative"] is True
    assert chart["checklist"]["macd_minus_cross"] is True

    listed = client.get("/api/charts/TSLA").get_json()["charts"][0]
    assert listed["analysis"]["status"] == "completed"
    assert "Trend is consolidating." in listed["analysis"]["text"]
    assert "Checklist verdicts:" in listed["analysis"]["text"]


def test_analyze_chart_captures_failures(client, png_file, monkeypatch):
    fileobj, filename = png_file
    response = upload_chart(client, fileobj, filename, ticker="AMD")
    assert response.status_code == 201

    def fake_analyze(self, image_bytes, prompt, system_prompt=""):
        raise RuntimeError("model timeout")

    monkeypatch.setattr("charts_api.ai_analysis.OpenAIChartAnalyzer.analyze_chart", fake_analyze)

    analyze = client.post(f"/api/charts/AMD/2026-02-11/{filename}/analyze")
    assert analyze.status_code == 200

    chart = analyze.get_json()["chart"]
    assert chart["analysis"]["status"] == "failed"
    assert chart["analysis"]["error"] == "model timeout"


def test_analyze_chart_still_completes_when_checklist_pass_fails(client, png_file, monkeypatch):
    fileobj, filename = png_file
    response = upload_chart(client, fileobj, filename, ticker="MSFT", notes="Second pass fallback")
    assert response.status_code == 201

    def fake_analyze(self, image_bytes, prompt, system_prompt=""):
        assert image_bytes.startswith(b"\x89PNG")
        if "Analyze this trading chart image" in prompt:
            return {"analysis_text": "Primary analysis only.", "analysis_model": "gpt-5.2"}
        raise RuntimeError("checklist timeout")

    monkeypatch.setattr("charts_api.ai_analysis.OpenAIChartAnalyzer.analyze_chart", fake_analyze)

    analyze = client.post(f"/api/charts/MSFT/2026-02-11/{filename}/analyze")
    assert analyze.status_code == 200

    chart = analyze.get_json()["chart"]
    assert chart["analysis"]["status"] == "completed"
    assert chart["analysis"]["text"] == "Primary analysis only."
    assert chart["checklist"]["red_candle"] is True
    assert chart["checklist"]["yellow_candle"] is True


def test_cycle_timeframe_endpoint(client, png_file):
    fileobj, filename = png_file
    response = upload_chart(client, fileobj, filename, ticker="QQQ", timeframe="D")
    assert response.status_code == 201

    first = client.post(f"/api/charts/QQQ/2026-02-11/{filename}/timeframe")
    assert first.status_code == 200
    assert first.get_json()["chart"]["timeframe"] == "W"

    second = client.post(f"/api/charts/QQQ/2026-02-11/{filename}/timeframe")
    assert second.status_code == 200
    assert second.get_json()["chart"]["timeframe"] == "M"

    third = client.post(f"/api/charts/QQQ/2026-02-11/{filename}/timeframe")
    assert third.status_code == 200
    assert third.get_json()["chart"]["timeframe"] == "D"

    listed = client.get("/api/charts/QQQ").get_json()["charts"][0]
    assert listed["timeframe"] == "D"
