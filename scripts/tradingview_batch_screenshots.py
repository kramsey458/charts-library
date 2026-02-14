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
  APPLY_STEALTH_DURING_LOGIN=true|false (default: false)
  HEADLESS=true|false (default: false)
  OUTPUT_DIR=./downloads (default: ./downloads)
  AUTO_CONFIRM_LOGIN=true|false (default: false)
  POST_NAVIGATION_WAIT_MS=900
  SEARCH_RESULTS_WAIT_MS=180
  SYMBOL_LOAD_TIMEOUT_MS=12000
  CHART_RENDER_WAIT_MS=900
  INTER_TICKER_DELAY_MS=80
"""

from __future__ import annotations

import argparse
import os
import platform
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import List

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright

try:
    from playwright_stealth import Stealth
except ImportError:  # pragma: no cover - optional dependency for stealth hardening
    Stealth = None


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


def timestamp_slug() -> str:
    return datetime.now(timezone.utc).isoformat().replace(":", "-").replace(".", "-")


def wait_ms(page, duration_ms: int) -> None:
    page.wait_for_timeout(max(0, duration_ms))


def focus_chart(page) -> None:
    try:
        page.keyboard.press("Escape")
    except PlaywrightError:
        pass

    viewport = page.viewport_size or {"width": 1280, "height": 720}
    page.mouse.click(int(viewport["width"] * 0.5), int(viewport["height"] * 0.5))
    wait_ms(page, 60)


def parse_int_env(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default

    try:
        value = int(raw.strip())
    except ValueError as exc:  # pragma: no cover - defensive parsing
        raise ValueError(f"{name} must be an integer; got {raw!r}") from exc

    return max(0, value)


def wait_for_ticker_loaded(page, ticker: str, timeout_ms: int) -> None:
    uppercase_ticker = ticker.upper()
    page.wait_for_function(
        """
        (symbol) => document.title.toUpperCase().includes(symbol)
        """,
        arg=uppercase_ticker,
        timeout=timeout_ms,
    )


def select_first_symbol_result(
    page,
    ticker: str,
    search_results_wait_ms: int,
    symbol_load_timeout_ms: int,
    chart_render_wait_ms: int,
) -> None:
    focus_chart(page)

    # Type the ticker directly on keyboard; TradingView should auto-open symbol search.
    page.keyboard.type(ticker)

    # Give the search window/results time to populate, then select first result.
    wait_ms(page, search_results_wait_ms)
    page.keyboard.press("Enter")

    # Wait for chart symbol switch, then give TradingView extra time to finish rendering.
    wait_for_ticker_loaded(page, ticker=ticker, timeout_ms=symbol_load_timeout_ms)
    wait_ms(page, chart_render_wait_ms)


def trigger_save_shortcut(page) -> None:
    is_mac = platform.system().lower() == "darwin"
    shortcut = "Alt+Meta+S" if is_mac else "Control+Alt+S"
    wait_ms(page, 40)
    page.keyboard.press(shortcut)


def build_launch_args(headless: bool) -> list[str]:
    args = [
        "--disable-blink-features=AutomationControlled",
        "--lang=en-US,en;q=0.9",
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


def apply_stealth(page) -> None:
    page.add_init_script(
        """
        Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
        window.chrome = window.chrome || { runtime: {} };
        Object.defineProperty(navigator, 'hardwareConcurrency', { get: () => 8 });
        Object.defineProperty(navigator, 'deviceMemory', { get: () => 8 });
        """
    )

    if Stealth is None:
        print(
            "[WARN] playwright-stealth not installed; using built-in stealth tweaks only.",
            file=sys.stderr,
        )
        return

    Stealth().apply_stealth_sync(page)


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

    filename = f"{ticker}_{timestamp_slug()}.png"
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
    wait_ms(page, parse_int_env("POST_NAVIGATION_WAIT_MS", 900))

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
        wait_ms(page, parse_int_env("POST_NAVIGATION_WAIT_MS", 900))

        if not looks_like_login_page(page.url):
            print(f"Auth check passed on page: {page.url}")
            return


def parse_bool_env(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() == "true"


def should_apply_stealth_during_login() -> bool:
    return parse_bool_env("APPLY_STEALTH_DURING_LOGIN", False)


def main() -> int:
    args = parse_args()
    tickers = load_tickers(args)

    if not tickers:
        raise ValueError("Ticker list is empty.")

    output_dir = Path(os.getenv("OUTPUT_DIR", "downloads")).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    url = os.getenv("TRADINGVIEW_URL", "https://www.tradingview.com/chart/")
    headless = parse_bool_env("HEADLESS", False)
    search_results_wait_ms = parse_int_env("SEARCH_RESULTS_WAIT_MS", 180)
    symbol_load_timeout_ms = parse_int_env("SYMBOL_LOAD_TIMEOUT_MS", 12000)
    chart_render_wait_ms = parse_int_env("CHART_RENDER_WAIT_MS", 900)
    inter_ticker_delay_ms = parse_int_env("INTER_TICKER_DELAY_MS", 80)

    with sync_playwright() as p:
        launch_args = build_launch_args(headless=headless)
        browser = p.chromium.launch(headless=headless, args=launch_args)

        context = browser.new_context(**build_context_options(headless=headless))
        page = context.new_page()

        stealth_pre_login = should_apply_stealth_during_login()
        if stealth_pre_login:
            print("Applying stealth before login (APPLY_STEALTH_DURING_LOGIN=true).")
            apply_stealth(page)
        else:
            print(
                "Stealth is deferred until after manual login/captcha to avoid reCAPTCHA stalls. "
                "Set APPLY_STEALTH_DURING_LOGIN=true to override."
            )

        try:
            open_login_flow_if_configured(page, chart_url=url)
            confirm_logged_in(headless=headless)

            if not stealth_pre_login:
                apply_stealth(page)

            if parse_bool_env("START_ON_LOGIN", True):
                print(f"Navigating to chart page: {url}")
                page.goto(url, wait_until="domcontentloaded", timeout=90000)
                wait_ms(page, parse_int_env("POST_NAVIGATION_WAIT_MS", 900))

            enforce_auth_first(page, chart_url=url, headless=headless)

            saved_paths: List[Path] = []

            for i, ticker in enumerate(tickers):
                print(f"\n[{i + 1}/{len(tickers)}] Processing {ticker}")
                select_first_symbol_result(
                    page,
                    ticker,
                    search_results_wait_ms=search_results_wait_ms,
                    symbol_load_timeout_ms=symbol_load_timeout_ms,
                    chart_render_wait_ms=chart_render_wait_ms,
                )
                out_path = save_chart_image(page, output_dir, ticker)

                if out_path:
                    saved_paths.append(out_path)
                    print(f"Saved: {out_path}")

                wait_ms(page, inter_ticker_delay_ms)

            print("\nDone.")
            if saved_paths:
                print("Saved files:")
                for file_path in saved_paths:
                    print(f" - {file_path}")
            else:
                print("No downloadable files were detected.")
        finally:
            context.close()
            browser.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
