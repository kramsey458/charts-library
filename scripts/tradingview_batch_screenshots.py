#!/usr/bin/env python3
"""Batch-download TradingView chart images by typing ticker symbols directly.

Strategy implemented:
1) Type ticker characters directly on the chart (auto-opens symbol search).
2) Select the first result (Enter).
3) Trigger Ctrl+Alt+S to save/download image.
4) Repeat for all tickers.

Usage:
  python scripts/tradingview_batch_screenshots.py --tickers LPTH,AAPL,MSFT
  python scripts/tradingview_batch_screenshots.py --tickers-file ./tickers.txt

Optional env vars:
  TRADINGVIEW_URL (default: https://www.tradingview.com/chart/)
  TRADINGVIEW_LOGIN_URL (default: https://www.tradingview.com/accounts/signin/)
  START_ON_LOGIN=true|false (default: true)
  AUTH_FIRST_MODE=true|false (default: true)
  HEADLESS=true|false (default: false)
  OUTPUT_DIR=./downloads (default: ./downloads)
  AUTO_CONFIRM_LOGIN=true|false (default: false)
  PATCHRIGHT_CHANNEL=chrome|chromium (default: chrome)
  PATCHRIGHT_USER_DATA_DIR=~/.cache/charts-library/patchright (default shown)
  HOLD_AFTER_LOGIN_SECONDS=2 (default: 2, adds a small settle delay after manual login)
"""

from __future__ import annotations

import argparse
import math
import random
import os
import platform
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import List

from patchright.sync_api import Error as PlaywrightError
from patchright.sync_api import TimeoutError as PlaywrightTimeoutError
from patchright.sync_api import sync_playwright


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Batch-save TradingView chart images for a list of tickers."
    )
    source_group = parser.add_mutually_exclusive_group(required=True)
    source_group.add_argument("--tickers", help="Comma-separated tickers, e.g. LPTH,AAPL,MSFT")
    source_group.add_argument("--tickers-file", help="File with one ticker per line")
    args = parser.parse_args()

    return args


def load_tickers(args: argparse.Namespace) -> List[str]:
    if args.tickers:
        return [token.strip().upper() for token in args.tickers.split(",") if token.strip()]

    tickers_file = Path(args.tickers_file).expanduser().resolve()
    lines = tickers_file.read_text(encoding="utf-8").splitlines()
    return [
        line.strip().upper()
        for line in lines
        if line.strip() and not line.strip().startswith("#")
    ]


def current_utc_date_slug() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def human_pause(page, low_ms: int = 40, high_ms: int = 120) -> None:
    page.wait_for_timeout(random.randint(low_ms, high_ms))


def jitter_mouse(page) -> None:
    viewport = page.viewport_size or {"width": 1280, "height": 720}
    width = viewport["width"]
    height = viewport["height"]
    start_x = random.randint(int(width * 0.25), int(width * 0.75))
    start_y = random.randint(int(height * 0.25), int(height * 0.75))
    end_x = random.randint(int(width * 0.3), int(width * 0.7))
    end_y = random.randint(int(height * 0.3), int(height * 0.7))

    steps = random.randint(2, 4)
    for i in range(steps):
        t = i / max(steps - 1, 1)
        wiggle_x = math.sin(t * math.pi * 2) * random.uniform(0.7, 2.2)
        wiggle_y = math.cos(t * math.pi * 2) * random.uniform(0.7, 2.2)
        x = start_x + (end_x - start_x) * t + wiggle_x
        y = start_y + (end_y - start_y) * t + wiggle_y
        page.mouse.move(x, y)
        page.wait_for_timeout(random.randint(2, 8))


def focus_chart(page) -> None:
    jitter_mouse(page)
    try:
        page.keyboard.press("Escape")
    except PlaywrightError:
        pass

    viewport = page.viewport_size or {"width": 1280, "height": 720}
    page.mouse.click(int(viewport["width"] * 0.5), int(viewport["height"] * 0.5))
    human_pause(page)


def select_first_symbol_result(page, ticker: str) -> None:
    focus_chart(page)

    # Type the ticker directly on keyboard; TradingView should auto-open symbol search.
    page.keyboard.type(ticker, delay=random.randint(14, 30))

    # Give the search window/results time to populate, then select first result.
    human_pause(page, 60, 160)
    page.keyboard.press("Enter")

    wait_for_chart_ready(page, ticker)


def wait_for_chart_ready(page, ticker: str, timeout_ms: int = 8000) -> None:
    # Wait until at least one chart canvas is visible.
    try:
        page.wait_for_selector("canvas", state="visible", timeout=min(timeout_ms, 5000))
    except PlaywrightTimeoutError:
        print(f"[WARN] Chart canvas did not become visible for {ticker}.", file=sys.stderr)

    # Wait until page title reflects the selected ticker (best-effort).
    try:
        page.wait_for_function(
            "(symbol) => document.title.toUpperCase().includes(symbol)",
            ticker.upper(),
            timeout=min(timeout_ms, 7000),
        )
    except PlaywrightTimeoutError:
        print(
            f"[WARN] Page title did not update to {ticker} before timeout; continuing.",
            file=sys.stderr,
        )

    # Wait for known loading indicators to disappear.
    indicator_script = """
    () => {
      const selectors = [
        '[data-name="loading-spinner"]',
        '[data-name="series-status"]',
        '.chart-loading-screen',
        '.tv-spinner',
      ];
      const isVisible = (el) => {
        const style = window.getComputedStyle(el);
        return style && style.visibility !== 'hidden' && style.display !== 'none' && el.offsetParent !== null;
      };
      return selectors
        .flatMap((selector) => Array.from(document.querySelectorAll(selector)))
        .filter(isVisible)
        .length;
    }
    """

    stable_checks = 0
    deadline = time.monotonic() + (timeout_ms / 1000)
    while time.monotonic() < deadline:
        visible_indicators = page.evaluate(indicator_script)
        if visible_indicators == 0:
            stable_checks += 1
            if stable_checks >= 2:
                break
        else:
            stable_checks = 0
        page.wait_for_timeout(80)

    if stable_checks < 2:
        print(
            f"[WARN] Loading indicators remained visible for {ticker}; saving anyway.",
            file=sys.stderr,
        )

    human_pause(page, 35, 90)


def trigger_save_shortcut(page) -> None:
    is_mac = platform.system().lower() == "darwin"
    shortcut = "Alt+Meta+S" if is_mac else "Control+Alt+S"
    human_pause(page, 30, 90)
    page.keyboard.press(shortcut)


def build_launch_args(headless: bool) -> list[str]:
    args = [
        "--lang=en-US,en;q=0.9",
        "--disable-infobars",
    ]
    if not headless:
        # Fullscreen window for interactive login/captcha and chart operation.
        args.extend(["--start-maximized", "--start-fullscreen"])
    return args


def build_context_options(headless: bool) -> dict:
    base_options = {
        "accept_downloads": True,
        "locale": "en-US",
        "timezone_id": "America/New_York",
        "color_scheme": "dark",
    }
    if headless:
        base_options["viewport"] = {"width": 1920, "height": 1080}
        base_options["device_scale_factor"] = 1
    else:
        # Use the native fullscreen browser window size in headed mode.
        base_options["no_viewport"] = True
    return base_options


def save_chart_image(page, output_dir: Path, ticker: str) -> Path | None:
    try:
        with page.expect_download(timeout=20000) as download_info:
            trigger_save_shortcut(page)
        download = download_info.value
    except PlaywrightTimeoutError:
        print(
            f"[WARN] No download detected for {ticker}. "
            "Shortcut may have opened a system dialog or popup.",
            file=sys.stderr,
        )
        return None

    filename = f"{ticker},{current_utc_date_slug()}.png"
    out_path = output_dir / filename
    download.save_as(str(out_path))
    return out_path


def confirm_logged_in(headless: bool) -> None:
    auto_confirm = parse_bool_env("AUTO_CONFIRM_LOGIN", False)

    if headless:
        if auto_confirm:
            print("AUTO_CONFIRM_LOGIN=true set; skipping login prompt in headless mode.")
            return
        raise RuntimeError(
            "HEADLESS=true does not allow manual login confirmation prompts. "
            "Set HEADLESS=false for interactive login or set AUTO_CONFIRM_LOGIN=true "
            "if you already have persisted auth state."
        )

    print("\nPlease complete TradingView login/cookie consent in the opened browser window.")
    print("If you use Google login, finish the full Google OAuth flow in this browser window first.")
    print("When finished, type 'y' and press Enter to continue.")

    while True:
        response = input("Logged in and ready? [y/N]: ").strip().lower()
        if response in {"y", "yes"}:
            return
        print("Waiting for login confirmation. Type 'y' when you are ready.")


def open_login_flow_if_configured(page, chart_url: str) -> None:
    start_on_login = parse_bool_env("START_ON_LOGIN", True)
    login_url = os.getenv(
        "TRADINGVIEW_LOGIN_URL", "https://www.tradingview.com/accounts/signin/"
    )
    initial_url = login_url if start_on_login else chart_url

    print(f"Opening {initial_url}")
    page.goto(initial_url, wait_until="domcontentloaded", timeout=90000)
    human_pause(page, 900, 2000)

    if start_on_login:
        print("After login/captcha is complete, the script will navigate to the chart page.")


def looks_like_login_page(url: str) -> bool:
    lowered = (url or "").lower()
    return any(token in lowered for token in ("/accounts/signin", "captcha", "challenge"))


def enforce_auth_first(page, chart_url: str, headless: bool) -> None:
    if not parse_bool_env("AUTH_FIRST_MODE", True):
        return

    print("Auth-first mode is enabled. Verifying authenticated session before automation...")

    while True:
        current_url = page.url
        if not looks_like_login_page(current_url):
            print(f"Auth check passed on page: {current_url}")
            return

        if headless and parse_bool_env("AUTO_CONFIRM_LOGIN", False):
            print(
                "[WARN] Could not verify authenticated session in headless mode. "
                "Proceeding because AUTO_CONFIRM_LOGIN=true."
            )
            return

        print(
            "Still on login/captcha page. Complete challenge, "
            "then press Enter to retry auth check."
        )
        response = input(
            "Press Enter when auth is complete (or type 'skip' to continue anyway): "
        ).strip().lower()
        if response == "skip":
            print("[WARN] Proceeding without confirmed auth because user chose skip.")
            return

        print(f"Checking chart access: {chart_url}")
        page.goto(chart_url, wait_until="domcontentloaded", timeout=90000)
        human_pause(page, 900, 2000)

        if not looks_like_login_page(page.url):
            print(f"Auth check passed on page: {page.url}")
            return


def parse_bool_env(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() == "true"


def parse_int_env(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        value = int(raw.strip())
    except ValueError:
        return default
    return max(value, 0)


def resolve_patchright_user_data_dir() -> Path:
    raw = os.getenv("PATCHRIGHT_USER_DATA_DIR", "~/.cache/charts-library/patchright")
    directory = Path(raw).expanduser().resolve()
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def resolve_patchright_channel() -> str:
    raw = os.getenv("PATCHRIGHT_CHANNEL", "chrome").strip().lower()
    if raw not in {"chrome", "chromium"}:
        print(
            f"[WARN] Unsupported PATCHRIGHT_CHANNEL={raw!r}; falling back to 'chrome'.",
            file=sys.stderr,
        )
        return "chrome"
    return raw


def main() -> int:
    args = parse_args()
    tickers = load_tickers(args)

    if not tickers:
        raise ValueError("Ticker list is empty.")

    output_dir = Path(os.getenv("OUTPUT_DIR", "downloads")).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    url = os.getenv("TRADINGVIEW_URL", "https://www.tradingview.com/chart/")
    headless = parse_bool_env("HEADLESS", False)

    with sync_playwright() as p:
        launch_args = build_launch_args(headless=headless)
        channel = resolve_patchright_channel()
        user_data_dir = resolve_patchright_user_data_dir()

        print(
            "Launching Patchright persistent context "
            f"(channel={channel}, user_data_dir={user_data_dir})"
        )
        context = p.chromium.launch_persistent_context(
            str(user_data_dir),
            channel=channel,
            headless=headless,
            args=launch_args,
            ignore_default_args=["--enable-automation"],
            **build_context_options(headless=headless),
        )
        page = context.pages[0] if context.pages else context.new_page()

        try:
            open_login_flow_if_configured(page, chart_url=url)
            confirm_logged_in(headless=headless)
            hold_after_login_seconds = parse_int_env("HOLD_AFTER_LOGIN_SECONDS", 2)
            if hold_after_login_seconds:
                print(
                    f"Waiting {hold_after_login_seconds}s after manual login to let account state settle..."
                )
                page.wait_for_timeout(hold_after_login_seconds * 1000)

            if parse_bool_env("START_ON_LOGIN", True):
                print(f"Navigating to chart page: {url}")
                page.goto(url, wait_until="domcontentloaded", timeout=90000)
                human_pause(page, 900, 2000)

            enforce_auth_first(page, chart_url=url, headless=headless)

            saved_paths: List[Path] = []

            for i, ticker in enumerate(tickers):
                print(f"\n[{i + 1}/{len(tickers)}] Processing {ticker}")
                select_first_symbol_result(page, ticker)
                out_path = save_chart_image(page, output_dir, ticker)

                if out_path:
                    saved_paths.append(out_path)
                    print(f"Saved: {out_path}")

                human_pause(page, 20, 60)

            print("\nDone.")
            if saved_paths:
                print("Saved files:")
                for file_path in saved_paths:
                    print(f" - {file_path}")
            else:
                print("No downloadable files were detected.")
        finally:
            context.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
