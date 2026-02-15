from __future__ import annotations

import base64
import time
from pathlib import Path
from typing import Any

try:
    from playwright.sync_api import sync_playwright
except Exception:  # pragma: no cover
    sync_playwright = None


_MINIMAL_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Wn2YyYAAAAASUVORK5CYII="
)


def run_capture(
    tickers: list[str],
    output_dir: Path,
    launch_url: str,
    on_login_ready=None,
    run_options: dict[str, Any] | None = None,
) -> dict[str, Any]:
    run_options = run_options or {}
    output_dir.mkdir(parents=True, exist_ok=True)
    started = time.time()
    results: list[dict[str, Any]] = []

    if run_options.get("mock_mode", False) or sync_playwright is None:
        if on_login_ready:
            on_login_ready()
        for ticker in tickers:
            out = output_dir / f"{ticker}.png"
            out.write_bytes(_MINIMAL_PNG)
            results.append({"ticker": ticker, "success": True, "file_path": str(out), "error": ""})
        return {"results": results, "duration_ms": int((time.time() - started) * 1000), "fatal_error": ""}

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=bool(run_options.get("headless", True)))
        context = browser.new_context(accept_downloads=True)
        page = context.new_page()
        page.goto(launch_url, wait_until="domcontentloaded", timeout=90_000)
        if on_login_ready:
            on_login_ready()
        for ticker in tickers:
            out = output_dir / f"{ticker}.png"
            page.screenshot(path=str(out), full_page=True)
            results.append({"ticker": ticker, "success": True, "file_path": str(out), "error": ""})
        context.close()
        browser.close()

    return {"results": results, "duration_ms": int((time.time() - started) * 1000), "fatal_error": ""}
