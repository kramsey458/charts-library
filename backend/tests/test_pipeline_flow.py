from __future__ import annotations

import io
import time
from datetime import datetime, timedelta, timezone


def _create_job(client, text="AAPL\nmsft\n#comment\nBAD$\n"):
    return client.post("/api/pipeline/jobs", json={"tickers_text": text}, headers={"X-Owner-Id": "alice"})


def test_ticker_file_parsing_and_invalid_rows(client):
    data = {"ticker_file": (io.BytesIO(b"AAPL\n\n#note\nmsft\nBAD$\n"), "tickers.txt")}
    response = client.post("/api/pipeline/jobs", data=data, content_type="multipart/form-data", headers={"X-Owner-Id": "alice"})
    assert response.status_code == 201
    payload = response.get_json()
    assert payload["tickers"] == ["AAPL", "MSFT"]
    assert payload["invalid_rows"][0]["line"] == 5


def test_login_ownership_expiry_and_resume_idempotency(client):
    create = _create_job(client)
    job_id = create.get_json()["id"]
    start = client.post(f"/api/pipeline/jobs/{job_id}/start", headers={"X-Owner-Id": "alice"})
    assert start.status_code == 200
    launch_url = start.get_json()["launch_url"]

    forbidden = client.get(launch_url, headers={"X-Owner-Id": "bob"})
    assert forbidden.status_code == 403
    assert forbidden.get_json()["error"]["code"] == "FORBIDDEN"

    ok = client.get(launch_url, headers={"X-Owner-Id": "alice"})
    assert ok.status_code == 302
    assert "tradingview.com" in ok.headers["Location"]

    resume = client.post(f"/api/pipeline/jobs/{job_id}/resume-after-login", headers={"X-Owner-Id": "alice"})
    assert resume.status_code == 200
    second_resume = client.post(f"/api/pipeline/jobs/{job_id}/resume-after-login", headers={"X-Owner-Id": "alice"})
    assert second_resume.status_code == 200

    app = client.application
    pipeline = app.extensions["pipeline_service"]
    job = pipeline.repo.get_job(job_id)
    session = pipeline.repo.get_session(job.login_session_id)
    session.expires_at = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()
    pipeline.repo.save_session(session)

    create2 = _create_job(client, "TSLA\n")
    job2 = create2.get_json()["id"]
    start2 = client.post(f"/api/pipeline/jobs/{job2}/start", headers={"X-Owner-Id": "alice"}).get_json()
    session_url2 = start2["launch_url"]
    client.get(session_url2, headers={"X-Owner-Id": "alice"})
    job_obj2 = pipeline.repo.get_job(job2)
    sess2 = pipeline.repo.get_session(job_obj2.login_session_id)
    sess2.expires_at = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()
    pipeline.repo.save_session(sess2)
    expired = client.post(f"/api/pipeline/jobs/{job2}/resume-after-login", headers={"X-Owner-Id": "alice"})
    assert expired.status_code == 400
    assert expired.get_json()["error"]["code"] == "SESSION_EXPIRED"


def test_classify_and_upload_decision_gate(client, monkeypatch):
    from charts_api.pipeline import service as pipeline_service_module

    monkeypatch.setattr(
        pipeline_service_module,
        "classify_candle",
        lambda _bytes: {"label": "red", "scores": {"red_pixels": 5, "yellow_pixels": 0}},
    )

    create = _create_job(client, "AAPL\nMSFT\n")
    job_id = create.get_json()["id"]
    start = client.post(f"/api/pipeline/jobs/{job_id}/start", headers={"X-Owner-Id": "alice"}).get_json()
    client.get(start["launch_url"], headers={"X-Owner-Id": "alice"})
    client.post(f"/api/pipeline/jobs/{job_id}/resume-after-login", headers={"X-Owner-Id": "alice"})

    deadline = time.time() + 5
    state = ""
    while time.time() < deadline:
        job = client.get(f"/api/pipeline/jobs/{job_id}", headers={"X-Owner-Id": "alice"}).get_json()
        state = job["state"]
        if state == "awaiting_upload_decision":
            break
        time.sleep(0.1)
    assert state == "awaiting_upload_decision"

    decision = client.post(
        f"/api/pipeline/jobs/{job_id}/upload-decision",
        json={"policy": {"upload_red": True, "upload_yellow": False, "skip_none": True}, "overrides": {"MSFT": "skip"}},
        headers={"X-Owner-Id": "alice"},
    )
    assert decision.status_code == 200

    deadline = time.time() + 5
    final_state = ""
    while time.time() < deadline:
        job = client.get(f"/api/pipeline/jobs/{job_id}", headers={"X-Owner-Id": "alice"}).get_json()
        final_state = job["state"]
        if final_state in {"completed", "failed"}:
            break
        time.sleep(0.1)
    assert final_state == "completed"
    uploaded = [item for item in job["items"] if item["upload_status"] == "uploaded"]
    assert len(uploaded) == 1


def test_pipeline_create_job_allows_trailing_slash(client):
    response = client.post("/api/pipeline/jobs/", json={"tickers_text": "AAPL\n"}, headers={"X-Owner-Id": "alice"})
    assert response.status_code == 201
    assert response.get_json()["tickers"] == ["AAPL"]


def test_open_login_redirects_to_configured_tradingview_url(client, monkeypatch):
    monkeypatch.setenv("TRADINGVIEW_LOGIN_URL", "https://example.com/signin")
    create = _create_job(client, "AAPL\n")
    job_id = create.get_json()["id"]
    start = client.post(f"/api/pipeline/jobs/{job_id}/start", headers={"X-Owner-Id": "alice"}).get_json()
    response = client.get(start["launch_url"], headers={"X-Owner-Id": "alice"})
    assert response.status_code == 302
    assert response.headers["Location"] == "https://example.com/signin"


def test_pipeline_capture_honors_env_options(client, monkeypatch):
    from charts_api.pipeline import service as pipeline_service_module

    captured = {}

    def fake_run_capture(tickers, output_dir, launch_url, on_login_ready=None, run_options=None):
        captured["tickers"] = tickers
        captured["launch_url"] = launch_url
        captured["run_options"] = run_options or {}
        png_path = output_dir / "AAPL.png"
        png_path.parent.mkdir(parents=True, exist_ok=True)
        png_path.write_bytes(b"\x89PNG\r\n\x1a\n" + b"0" * 64)
        return {"results": [{"ticker": "AAPL", "success": True, "file_path": str(png_path), "error": ""}], "fatal_error": "", "duration_ms": 1}

    monkeypatch.setattr(pipeline_service_module, "run_capture", fake_run_capture)
    monkeypatch.setenv("PIPELINE_CAPTURE_MOCK", "false")
    monkeypatch.setenv("PIPELINE_CAPTURE_HEADLESS", "true")
    monkeypatch.setenv("PIPELINE_CAPTURE_BROWSER_CHANNEL", "chrome")
    monkeypatch.setenv("PIPELINE_CAPTURE_FRESH_PROFILE", "true")
    monkeypatch.setenv("TRADINGVIEW_CHART_URL", "https://www.tradingview.com/chart/")

    create = _create_job(client, "AAPL\n")
    job_id = create.get_json()["id"]
    start = client.post(f"/api/pipeline/jobs/{job_id}/start", headers={"X-Owner-Id": "alice"}).get_json()
    client.get(start["launch_url"], headers={"X-Owner-Id": "alice"})
    client.post(f"/api/pipeline/jobs/{job_id}/resume-after-login", headers={"X-Owner-Id": "alice"})

    deadline = time.time() + 3
    while time.time() < deadline:
        job = client.get(f"/api/pipeline/jobs/{job_id}", headers={"X-Owner-Id": "alice"}).get_json()
        if job["state"] in {"awaiting_upload_decision", "completed", "failed"}:
            break
        time.sleep(0.05)

    assert captured["launch_url"] == "https://www.tradingview.com/chart/"
    assert captured["run_options"]["mock_mode"] is False
    assert captured["run_options"]["headless"] is True
    assert captured["run_options"]["browser_channel"] == "chrome"
    assert captured["run_options"]["fresh_profile"] is True
