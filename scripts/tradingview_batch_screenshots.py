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
  HEADLESS=true|false (default: false)
  OUTPUT_DIR=./downloads (default: ./downloads)
"""

from __future__ import annotations

import argparse
import os
import platform
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import List

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Batch-save TradingView chart images for a list of tickers."
    )
    parser.add_argument("--tickers", help="Comma-separated tickers, e.g. LPTH,AAPL,MSFT")
    parser.add_argument("--tickers-file", help="File with one ticker per line")
    args = parser.parse_args()

    if not args.tickers and not args.tickers_file:
        parser.error("Provide --tickers 'LPTH,AAPL' or --tickers-file ./tickers.txt")

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


def focus_chart(page) -> None:
    try:
        page.keyboard.press("Escape")
    except Exception:
        pass

    viewport = page.viewport_size or {"width": 1280, "height": 720}
    page.mouse.click(int(viewport["width"] * 0.5), int(viewport["height"] * 0.5))


def select_first_symbol_result(page, ticker: str) -> None:
    focus_chart(page)

    # Type the ticker directly on keyboard; TradingView should auto-open symbol search.
    page.keyboard.type(ticker, delay=80)

    # Give the search window/results time to populate, then select first result.
    page.wait_for_timeout(900)
    page.keyboard.press("Enter")

    # Allow chart to switch symbol.
    page.wait_for_timeout(1800)


def trigger_save_shortcut(page) -> None:
    is_mac = platform.system().lower() == "darwin"
    shortcut = "Alt+Meta+S" if is_mac else "Control+Alt+S"
    page.keyboard.press(shortcut)


def save_chart_image(page, output_dir: Path, ticker: str, index: int) -> Path | None:
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

    filename = f"{index + 1:02d}_{ticker}_{timestamp_slug()}.png"
    out_path = output_dir / filename
    download.save_as(str(out_path))
    return out_path


def confirm_logged_in() -> None:
    print("\nPlease complete TradingView login/cookie consent in the opened browser window.")
    print("When finished, type 'y' and press Enter to continue.")

    while True:
        response = input("Logged in and ready? [y/N]: ").strip().lower()
        if response in {"y", "yes"}:
            return
        print("Waiting for login confirmation. Type 'y' when you are ready.")


def parse_bool_env(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() == "true"


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
        browser = p.chromium.launch(
            headless=headless,
            args=["--start-maximized"] if not headless else None,
        )
        context = browser.new_context(
            accept_downloads=True,
            no_viewport=True if not headless else False,
            viewport=None if not headless else {"width": 1600, "height": 1000},
        )
        page = context.new_page()

        try:
            print(f"Opening {url}")
            page.goto(url, wait_until="domcontentloaded", timeout=90000)

            confirm_logged_in()

            saved_paths: List[Path] = []

            for i, ticker in enumerate(tickers):
                print(f"\n[{i + 1}/{len(tickers)}] Processing {ticker}")
                select_first_symbol_result(page, ticker)
                out_path = save_chart_image(page, output_dir, ticker, i)

                if out_path:
                    saved_paths.append(out_path)
                    print(f"Saved: {out_path}")

                page.wait_for_timeout(600)

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
