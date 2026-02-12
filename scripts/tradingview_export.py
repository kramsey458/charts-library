#!/usr/bin/env python3
"""Batch export TradingView chart images for a list of tickers.

Workflow:
1) Launch Chromium with a persistent profile (keeps TradingView login/session).
2) Load chart page and wait for user to finish one-time manual prep (layout, indicators).
3) For each ticker from a text file:
   - open symbol picker from top-left
   - type ticker and confirm
   - click top-right camera icon
   - click "Download image"
   - save the resulting PNG with the ticker name

This script intentionally includes selector and keyboard fallbacks because the
TradingView DOM can vary across UI versions/accounts.
"""

from __future__ import annotations

import argparse
import re
import sys
import time
from dataclasses import dataclass
from pathlib import Path

from playwright.sync_api import BrowserContext, Locator, Page, TimeoutError as PWTimeout, sync_playwright


@dataclass
class Config:
    tickers_file: Path
    output_dir: Path
    profile_dir: Path
    chart_url: str
    headless: bool
    delay_sec: float
    symbol_wait_ms: int
    dry_run: bool


def parse_args() -> Config:
    parser = argparse.ArgumentParser(description="Export TradingView chart images for each ticker in a text file.")
    parser.add_argument("--tickers", default="tickers.txt", help="Path to ticker list text file (one ticker per line).")
    parser.add_argument("--out", default="tv_exports", help="Directory where PNG files are saved.")
    parser.add_argument("--profile", default="tv_profile", help="Chromium user profile dir for persistent login.")
    parser.add_argument("--url", default="https://www.tradingview.com/chart/", help="TradingView chart URL.")
    parser.add_argument("--headless", action="store_true", help="Run headless. Usually keep this off for TradingView.")
    parser.add_argument("--delay", type=float, default=0.0, help="Delay between tickers in seconds.")
    parser.add_argument("--symbol-wait-ms", type=int, default=900, help="Wait time after changing symbol.")
    parser.add_argument("--dry-run", action="store_true", help="Read and print tickers without automating browser.")
    args = parser.parse_args()
    return Config(
        tickers_file=Path(args.tickers),
        output_dir=Path(args.out),
        profile_dir=Path(args.profile),
        chart_url=args.url,
        headless=args.headless,
        delay_sec=max(args.delay, 0.0),
        symbol_wait_ms=max(args.symbol_wait_ms, 0),
        dry_run=args.dry_run,
    )


def read_tickers(tickers_file: Path) -> list[str]:
    if not tickers_file.exists():
        raise FileNotFoundError(f"Ticker file not found: {tickers_file}")

    tickers: list[str] = []
    for raw in tickers_file.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        tickers.append(line.upper())

    if not tickers:
        raise ValueError(f"No tickers found in {tickers_file}")
    return tickers


def safe_name(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]", "_", text)


def try_click(page: Page, selectors: list[str], timeout_ms: int = 1200) -> str:
    """Click first visible selector; return matched selector."""
    errors: list[str] = []
    for selector in selectors:
        try:
            target = page.locator(selector).first
            target.wait_for(state="visible", timeout=timeout_ms)
            target.click(timeout=timeout_ms)
            return selector
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{selector}: {exc}")
    raise RuntimeError("No selector clicked:\n" + "\n".join(errors))


def ensure_chart_page(page: Page, chart_url: str) -> None:
    if "tradingview.com/chart" not in page.url:
        page.goto(chart_url, wait_until="domcontentloaded")
        page.wait_for_timeout(200)


def _symbol_search_dialog_open(page: Page) -> bool:
    dialog_signals = [
        '[data-name="symbol-search-dialog"]',
        '[data-name="symbol-search-items-dialog"]',
        '[role="dialog"]:has-text("Symbol Search")',
    ]
    for selector in dialog_signals:
        try:
            page.locator(selector).first.wait_for(state="visible", timeout=250)
            return True
        except Exception:  # noqa: BLE001
            continue
    return False


def _wrong_global_search_open(page: Page) -> bool:
    try:
        page.locator('text=/Search tool or function/i').first.wait_for(state="visible", timeout=150)
        return True
    except Exception:  # noqa: BLE001
        return False


def _close_wrong_global_search(page: Page) -> None:
    if _wrong_global_search_open(page):
        page.keyboard.press("Escape")
        page.wait_for_timeout(120)


def _first_visible(page: Page, selectors: list[str], timeout_ms: int = 500) -> Locator | None:
    for selector in selectors:
        target = page.locator(selector).first
        try:
            target.wait_for(state="visible", timeout=timeout_ms)
            return target
        except Exception:  # noqa: BLE001
            continue
    return None


def _open_symbol_search(page: Page) -> None:
    # Click only symbol-entry points from your layout (top-left symbol region).
    open_symbol_selectors = [
        '[data-name="header-toolbar-symbol-search"]',
        'button[aria-label*="Symbol Search"]',
        'button[title*="Symbol Search"]',
        '[data-name="legend-source-title"]',
        '[data-name="legend-source-item"]',
    ]

    for _ in range(5):
        if _symbol_search_dialog_open(page):
            return

        target = _first_visible(page, open_symbol_selectors, timeout_ms=450)
        if target is not None:
            try:
                target.click(timeout=450)
            except Exception:  # noqa: BLE001
                pass

        page.wait_for_timeout(120)

        if _wrong_global_search_open(page) and not _symbol_search_dialog_open(page):
            _close_wrong_global_search(page)
            # Re-attempt open from top-left symbol button immediately.
            target = _first_visible(page, open_symbol_selectors, timeout_ms=400)
            if target is not None:
                try:
                    target.click(timeout=400)
                except Exception:  # noqa: BLE001
                    pass
                page.wait_for_timeout(120)

        if _symbol_search_dialog_open(page):
            return

    # Keyboard fallback: use Ctrl+K only (avoid Ctrl+L browser address bar behavior).
    for _ in range(2):
        page.keyboard.press("Control+K")
        page.wait_for_timeout(140)
        if _wrong_global_search_open(page):
            _close_wrong_global_search(page)
            target = _first_visible(page, open_symbol_selectors, timeout_ms=400)
            if target is not None:
                try:
                    target.click(timeout=400)
                except Exception:  # noqa: BLE001
                    pass
                page.wait_for_timeout(120)
        if _symbol_search_dialog_open(page):
            return

    raise RuntimeError("Could not open TradingView Symbol Search dialog.")


def select_ticker(page: Page, ticker: str, symbol_wait_ms: int) -> None:
    # Retry once in case the dialog was opened but auto-closed by transient UI focus.
    for _ in range(2):
        _open_symbol_search(page)
        if _symbol_search_dialog_open(page):
            break
    if not _symbol_search_dialog_open(page):
        raise RuntimeError("Symbol Search did not remain open.")

    # Keep selectors scoped to symbol search dialog first.
    search_input_selectors = [
        '[data-name="symbol-search-dialog"] input[type="text"]',
        '[data-name="symbol-search-items-dialog"] input[type="text"]',
        'input[placeholder*="Symbol"]',
        'input[aria-label*="Symbol"]',
        '[role="dialog"] input[type="text"]',
    ]

    search_input = None
    for selector in search_input_selectors:
        candidate = page.locator(selector).first
        try:
            candidate.wait_for(state="visible", timeout=550)
            search_input = candidate
            break
        except Exception:  # noqa: BLE001
            continue

    if search_input is None:
        raise RuntimeError("Symbol Search opened, but symbol input was not found.")

    search_input.click(timeout=350)
    search_input.fill("")
    search_input.type(ticker, delay=0)

    # Give symbol results a brief moment to populate, then prefer first result row.
    result_row_selectors = [
        '[data-name="symbol-search-dialog"] [data-name="list-item"]',
        '[data-name="symbol-search-dialog"] [role="option"]',
        '[data-name="symbol-search-items-dialog"] [data-name="list-item"]',
        '[data-name="symbol-search-items-dialog"] [role="option"]',
    ]

    row_clicked = False
    for selector in result_row_selectors:
        row = page.locator(selector).first
        try:
            row.wait_for(state="visible", timeout=650)
            row.click(timeout=400)
            row_clicked = True
            break
        except Exception:  # noqa: BLE001
            continue

    if not row_clicked:
        # Fallback to Enter when rows are not directly clickable in this UI variant.
        page.keyboard.press("Enter")

    page.wait_for_timeout(symbol_wait_ms)


def download_image_for_ticker(page: Page, ticker: str, output_dir: Path) -> Path:
    camera_button_selectors = [
        '[data-name="screenshot"]',
        '[data-name="header-toolbar-screenshot"]',
        'button[aria-label*="Take a snapshot"]',
        'button[aria-label*="Snapshot"]',
    ]

    try_click(page, camera_button_selectors, timeout_ms=900)

    download_item_selectors = [
        'text=/^Download image$/i',
        'text=/Download image/i',
        'text=/Save image/i',
    ]

    last_error: Exception | None = None
    for selector in download_item_selectors:
        try:
            with page.expect_download(timeout=3500) as download_info:
                page.locator(selector).first.click(timeout=900)
            download = download_info.value
            out_path = output_dir / f"{safe_name(ticker)}.png"
            download.save_as(str(out_path))
            return out_path
        except Exception as exc:  # noqa: BLE001
            last_error = exc

    raise RuntimeError(f"Failed to click download image menu item. Last error: {last_error}")


def run_export(context: BrowserContext, config: Config, tickers: list[str]) -> int:
    page = context.pages[0] if context.pages else context.new_page()
    page.goto(config.chart_url, wait_until="domcontentloaded")

    print("Manual one-time prep:")
    print("  1) Log in to TradingView in this window.")
    print("  2) Open your preferred layout and indicator suite.")
    input("When chart is ready, press Enter to continue... ")

    ok = 0
    failed = 0

    for index, ticker in enumerate(tickers, start=1):
        print(f"[{index}/{len(tickers)}] {ticker}")
        try:
            select_ticker(page, ticker, config.symbol_wait_ms)
            out_file = download_image_for_ticker(page, ticker, config.output_dir)
            print(f"  ✅ Saved: {out_file}")
            ok += 1
        except PWTimeout as exc:
            print(f"  ❌ Timeout: {exc}")
            failed += 1
        except Exception as exc:  # noqa: BLE001
            print(f"  ❌ Failed: {exc}")
            failed += 1
        time.sleep(config.delay_sec)

    print(f"Finished. Success={ok}, Failed={failed}")
    return 0 if failed == 0 else 2


def main() -> int:
    config = parse_args()
    tickers = read_tickers(config.tickers_file)

    if config.dry_run:
        print("Tickers loaded:")
        for ticker in tickers:
            print(f"- {ticker}")
        return 0

    config.output_dir.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as playwright:
        context = playwright.chromium.launch_persistent_context(
            user_data_dir=str(config.profile_dir),
            headless=config.headless,
            accept_downloads=True,
            args=["--start-maximized"],
            no_viewport=True,
        )
        try:
            return run_export(context, config, tickers)
        finally:
            context.close()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("\nInterrupted by user.")
        raise SystemExit(130) from None
    except Exception as exc:  # noqa: BLE001
        print(f"Fatal error: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
