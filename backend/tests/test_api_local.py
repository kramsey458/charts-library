from __future__ import annotations

import io


def upload_chart(client, fileobj, filename, ticker="VG", date="2026-02-11", notes="Base case"):
    return client.post(
        "/api/charts",
        data={
            "ticker": ticker,
            "date": date,
            "notes": notes,
            "red_candle": "true",
            "trend_bullish": "false",
            "chart": (fileobj, filename),
        },
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

    tickers = client.get("/api/tickers").get_json()
    assert tickers["tickers"] == ["VG"]
    assert tickers["chart_counts"]["VG"] == 1

    charts = client.get("/api/charts/VG")
    assert charts.status_code == 200
    chart = charts.get_json()["charts"][0]
    assert chart["notes"] == "Initial VG note"

    patch = client.patch(
        f"/api/charts/VG/{chart['date']}/{chart['filename']}/notes",
        json={"notes": "Updated VG note", "checklist": {"trend_bullish": True}},
    )
    assert patch.status_code == 200
    patched_chart = patch.get_json()["chart"]
    assert patched_chart["notes"] == "Updated VG note"
    assert patched_chart["checklist"]["trend_bullish"] is True

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
