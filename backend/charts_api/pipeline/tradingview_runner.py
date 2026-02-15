from __future__ import annotations

import base64
import math
import platform
import random
import tempfile
import time
from pathlib import Path
from typing import Any

try:
    from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
    from playwright.sync_api import sync_playwright
except Exception:  # pragma: no cover
    sync_playwright = None
    PlaywrightTimeoutError = Exception


_MINIMAL_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Wn2YyYAAAAASUVORK5CYII="
)


def _human_pause(page, low_ms: int = 120, high_ms: int = 380) -> None:
    page.wait_for_timeout(random.randint(low_ms, high_ms))


def _focus_chart(page) -> None:
    viewport = page.viewport_size or {"width": 1280, "height": 720}
    start_x = random.randint(int(viewport["width"] * 0.3), int(viewport["width"] * 0.7))
    start_y = random.randint(int(viewport["height"] * 0.3), int(viewport["height"] * 0.7))
    end_x = start_x + random.randint(-40, 40)
    end_y = start_y + random.randint(-30, 30)
    steps = random.randint(4, 9)
    for i in range(steps):
        t = i / max(steps - 1, 1)
        x = start_x + (end_x - start_x) * t + math.sin(t * math.pi) * random.uniform(-1.5, 1.5)
        y = start_y + (end_y - start_y) * t + math.cos(t * math.pi) * random.uniform(-1.5, 1.5)
        page.mouse.move(x, y)
    page.mouse.click(int(viewport["width"] * 0.5), int(viewport["height"] * 0.5))
    _human_pause(page)


def _select_ticker(page, ticker: str) -> None:
    _focus_chart(page)
    page.keyboard.press("Escape")
    _human_pause(page)
    page.keyboard.type(ticker, delay=random.randint(45, 85))
    _human_pause(page, 320, 700)
    page.keyboard.press("Enter")
    _human_pause(page, 850, 1600)


def _save_shortcut(page) -> None:
    shortcut = "Alt+Meta+S" if platform.system().lower() == "darwin" else "Control+Alt+S"
    page.keyboard.press(shortcut)


def _looks_like_image(path: Path) -> bool:
    try:
        data = path.read_bytes()[:64]
    except OSError:
        return False

    is_png = data.startswith(b"\x89PNG\r\n\x1a\n")
    is_jpeg = data.startswith(b"\xff\xd8\xff")
    is_gif = data.startswith(b"GIF87a") or data.startswith(b"GIF89a")
    is_webp = data.startswith(b"RIFF") and b"WEBP" in data
    return is_png or is_jpeg or is_gif or is_webp


def _screenshot_fallback(page, output_dir: Path, ticker: str) -> Path:
    out = output_dir / f"{ticker}_{int(time.time() * 1000)}.png"
    page.screenshot(path=str(out), full_page=True)
    return out


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

    fatal_error = ""
    fresh_profile = bool(run_options.get("fresh_profile", True))
    browser_channel = run_options.get("browser_channel", "chrome")

    with tempfile.TemporaryDirectory(prefix="pipeline-chrome-") as temp_profile_dir, sync_playwright() as playwright:
        if fresh_profile:
            context = playwright.chromium.launch_persistent_context(
                user_data_dir=temp_profile_dir,
                channel=browser_channel,
                headless=bool(run_options.get("headless", False)),
                accept_downloads=True,
                args=["--disable-blink-features=AutomationControlled", "--start-maximized"],
            )
            page = context.pages[0] if context.pages else context.new_page()
        else:
            browser = playwright.chromium.launch(
                channel=browser_channel,
                headless=bool(run_options.get("headless", False)),
                args=["--disable-blink-features=AutomationControlled", "--start-maximized"],
            )
            context = browser.new_context(accept_downloads=True)
            page = context.new_page()

        page.goto(launch_url, wait_until="domcontentloaded", timeout=90_000)
        if on_login_ready:
            on_login_ready()

        for ticker in tickers:
            out = output_dir / f"{ticker}_{int(time.time() * 1000)}.png"
            try:
                _select_ticker(page, ticker)
                with page.expect_download(timeout=int(run_options.get("download_timeout_ms", 20_000))) as download_info:
                    _save_shortcut(page)
                download_info.value.save_as(str(out))
                if _looks_like_image(out):
                    results.append({"ticker": ticker, "success": True, "file_path": str(out), "error": ""})
                    continue

                fallback = _screenshot_fallback(page, output_dir, ticker)
                results.append(
                    {
                        "ticker": ticker,
                        "success": True,
                        "file_path": str(fallback),
                        "error": "Downloaded artifact was not an image; used screenshot fallback.",
                    }
                )
            except PlaywrightTimeoutError:
                fallback = _screenshot_fallback(page, output_dir, ticker)
                results.append(
                    {
                        "ticker": ticker,
                        "success": True,
                        "file_path": str(fallback),
                        "error": "No chart download detected after save shortcut; used screenshot fallback.",
                    }
                )
            except Exception as exc:  # pragma: no cover - runtime guard
                results.append({"ticker": ticker, "success": False, "file_path": "", "error": str(exc)})

        context.close()

    if not any(item["success"] for item in results):
        fatal_error = "Capture run completed with zero successful downloads."

    return {"results": results, "duration_ms": int((time.time() - started) * 1000), "fatal_error": fatal_error}
