#!/usr/bin/env python3
"""Batch-download TradingView chart images using Camoufox.

Flow implemented:
1) Launch a Camoufox browser (anti-detect from startup).
2) Block all automation until Google/TradingView login is complete.
3) Navigate to chart and type ticker symbols directly.
4) Trigger save shortcut and store downloaded images.

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
  LOGIN_TIMEOUT_SECONDS=900 (default)
"""

from __future__ import annotations

import argparse
import os
import platform
import random
from datetime import datetime, timezone
from pathlib import Path
from typing import List

from camoufox.sync_api import Camoufox
from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Batch-save TradingView chart images for a list of tickers."
    )
    source_group = parser.add_mutually_exclusive_group(required=True)
    source_group.add_argument("--tickers", help="Comma-separated tickers, e.g. LPTH,AAPL,MSFT")
    source_group.add_argument("--tickers-file", help="File with one ticker per line")
    return parser.parse_args()


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


def parse_bool_env(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() == "true"


def timestamp_slug() -> str:
    return datetime.now(timezone.utc).isoformat().replace(":", "-").replace(".", "-")


def short_pause(page, low_ms: int = 60, high_ms: int = 180) -> None:
    page.wait_for_timeout(random.randint(low_ms, high_ms))


def focus_chart(page) -> None:
    try:
        page.keyboard.press("Escape")
    except PlaywrightError:
        pass

    viewport = page.viewport_size or {"width": 1400, "height": 900}
    page.mouse.click(int(viewport["width"] * 0.5), int(viewport["height"] * 0.5))
    short_pause(page)


def select_first_symbol_result(page, ticker: str) -> None:
    focus_chart(page)
    page.keyboard.type(ticker, delay=random.randint(25, 45))
    short_pause(page, 140, 300)
    page.keyboard.press("Enter")
    short_pause(page, 480, 850)


def trigger_save_shortcut(page) -> None:
    shortcut = "Alt+Meta+S" if platform.system().lower() == "darwin" else "Control+Alt+S"
    short_pause(page, 70, 140)
    page.keyboard.press(shortcut)


def save_chart_image(page, output_dir: Path, ticker: str) -> Path | None:
    try:
        with page.expect_download(timeout=18000) as download_info:
            trigger_save_shortcut(page)
        download = download_info.value
    except PlaywrightTimeoutError:
        print(
            f"[WARN] No download detected for {ticker}. Shortcut may have opened a dialog.",
        )
        return None

    filename = f"{ticker}_{timestamp_slug()}.png"
    out_path = output_dir / filename
    download.save_as(str(out_path))
    return out_path


def looks_like_login_page(url: str) -> bool:
    lowered = (url or "").lower()
    return any(token in lowered for token in ("/accounts/signin", "captcha", "challenge", "auth"))


def tradingview_login_confirmed(page) -> bool:
    # Multiple signals so we are resilient to UI changes.
    selectors = [
        "[data-name='header-user-menu-button']",
        "[data-name='header-user-menu-button-signin']",
        "button[aria-label*='Profile']",
        "a[href*='/accounts/profile/']",
    ]

    for selector in selectors:
        try:
            if page.locator(selector).first.is_visible(timeout=300):
                # We only treat explicit sign-in button as not logged in.
                if "signin" in selector:
                    return False
                return True
        except PlaywrightError:
            continue

    if looks_like_login_page(page.url):
        return False

    return "/chart/" in page.url or "tradingview.com" in page.url


def wait_for_authenticated_session(page, chart_url: str, headless: bool) -> None:
    if not parse_bool_env("AUTH_FIRST_MODE", True):
        return

    login_timeout_seconds = int(os.getenv("LOGIN_TIMEOUT_SECONDS", "900"))

    if headless and not parse_bool_env("AUTO_CONFIRM_LOGIN", False):
        raise RuntimeError(
            "HEADLESS=true with AUTH_FIRST_MODE=true requires AUTO_CONFIRM_LOGIN=true "
            "or running headed mode for manual Google authentication."
        )

    print("Auth-first mode enabled: waiting for a verified authenticated TradingView session.")

    if headless and parse_bool_env("AUTO_CONFIRM_LOGIN", False):
        page.goto(chart_url, wait_until="domcontentloaded", timeout=90000)
        if not tradingview_login_confirmed(page):
            raise RuntimeError(
                "AUTO_CONFIRM_LOGIN=true but authentication could not be verified in headless mode."
            )
        return

    print("Complete Google/TradingView login in the opened browser window.")
    print("The script will not proceed until auth verification succeeds.")

    elapsed = 0
    while elapsed < login_timeout_seconds:
        user_input = input("Press Enter to verify login now (or type 'open' to load chart page): ").strip().lower()
        if user_input == "open":
            page.goto(chart_url, wait_until="domcontentloaded", timeout=90000)

        if tradingview_login_confirmed(page):
            print(f"Authenticated session confirmed at: {page.url}")
            return

        # Explicitly retry on chart page in case user finished login on popup provider tab.
        page.goto(chart_url, wait_until="domcontentloaded", timeout=90000)
        if tradingview_login_confirmed(page):
            print(f"Authenticated session confirmed at: {page.url}")
            return

        print("Auth not confirmed yet. Finish login/captcha/2FA and retry.")
        elapsed += 5

    raise TimeoutError("Timed out waiting for authenticated TradingView session.")


def main() -> int:
    args = parse_args()
    tickers = load_tickers(args)
    if not tickers:
        raise ValueError("Ticker list is empty.")

    output_dir = Path(os.getenv("OUTPUT_DIR", "downloads")).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    chart_url = os.getenv("TRADINGVIEW_URL", "https://www.tradingview.com/chart/")
    login_url = os.getenv("TRADINGVIEW_LOGIN_URL", "https://www.tradingview.com/accounts/signin/")
    start_on_login = parse_bool_env("START_ON_LOGIN", True)
    headless = parse_bool_env("HEADLESS", False)

    # Camoufox provides anti-detect hardening by design; we keep config minimal for speed.
    with Camoufox(
        headless=headless,
        humanize=0.35,
        block_webrtc=True,
        geoip=False,
        enable_cache=True,
        persistent_context=True,
    ) as context:
        page = context.new_page()

        initial_url = login_url if start_on_login else chart_url
        print(f"Opening {initial_url}")
        page.goto(initial_url, wait_until="domcontentloaded", timeout=90000)

        wait_for_authenticated_session(page, chart_url=chart_url, headless=headless)

        if start_on_login:
            page.goto(chart_url, wait_until="domcontentloaded", timeout=90000)
            short_pause(page, 250, 520)

        saved_paths: List[Path] = []
        for i, ticker in enumerate(tickers):
            print(f"\n[{i + 1}/{len(tickers)}] Processing {ticker}")
            select_first_symbol_result(page, ticker)
            out_path = save_chart_image(page, output_dir, ticker)
            if out_path:
                saved_paths.append(out_path)
                print(f"Saved: {out_path}")
            short_pause(page, 90, 220)

        print("\nDone.")
        if saved_paths:
            print("Saved files:")
            for file_path in saved_paths:
                print(f" - {file_path}")
        else:
            print("No downloadable files were detected.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
