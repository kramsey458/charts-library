#!/usr/bin/env python3
"""Scrape US/Canadian (+OTC) tickers and save local JSON for autocomplete/validation.

Uses public exchange pages/files (no paid APIs).
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import io
import json
import re
import urllib.request
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
OUTPUT_PATH = BASE_DIR / "data" / "valid_tickers.json"

USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)

SOURCES = {
    "nasdaq_listed": "https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt",
    "other_listed": "https://www.nasdaqtrader.com/dynamic/SymDir/otherlisted.txt",
    "tsx_companies": "https://www.tsx.com/json/company-directory/search/tsx/*",
    "tsxv_companies": "https://www.tsx.com/json/company-directory/search/tsxv/*",
}

VALID_TICKER_RE = re.compile(r"^[A-Z0-9.\-]{1,12}$")
OTC_TICKER_RE = re.compile(r"^[A-Z]{5}$")


def fetch_text(url: str) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=30) as response:
        return response.read().decode("utf-8", errors="replace")


def _clean_ticker(raw: str) -> str:
    return (raw or "").strip().upper()


def _infer_market(ticker: str, market: str) -> str:
    if market != "US":
        return market
    if OTC_TICKER_RE.match(ticker) and ticker.endswith("F"):
        return "OTC"
    return market


def _push(store: dict[str, dict], ticker: str, name: str, market: str) -> None:
    ticker_value = _clean_ticker(ticker)
    if not ticker_value or not VALID_TICKER_RE.match(ticker_value):
        return

    inferred_market = _infer_market(ticker_value, market)
    next_value = {
        "ticker": ticker_value,
        "name": (name or "").strip() or ticker_value,
        "market": inferred_market,
    }

    current = store.get(ticker_value)
    if current is None:
        store[ticker_value] = next_value
        return

    # Prefer richer name and more specific market labels.
    if len(next_value["name"]) > len(current.get("name", "")):
        current["name"] = next_value["name"]
    if current.get("market") == "US" and inferred_market != "US":
        current["market"] = inferred_market


def parse_pipe_symbol_file(payload: str, symbol_col: str, name_col: str, market: str) -> dict[str, dict]:
    rows = csv.DictReader(io.StringIO(payload), delimiter="|")
    parsed: dict[str, dict] = {}
    for row in rows:
        if (row.get(symbol_col) or "").startswith("File Creation Time"):
            continue
        _push(parsed, row.get(symbol_col, ""), row.get(name_col, ""), market)
    return parsed


def parse_tmx_json(payload: str, market: str) -> dict[str, dict]:
    parsed: dict[str, dict] = {}
    body = json.loads(payload)
    entries = body if isinstance(body, list) else body.get("results", [])
    for item in entries:
        ticker = (item.get("symbol") or item.get("ticker") or "").strip().upper()
        name = (item.get("name") or item.get("companyName") or "").strip()
        _push(parsed, ticker, name, market)
    return parsed


def load_existing_catalog() -> dict[str, dict]:
    if not OUTPUT_PATH.exists() or not OUTPUT_PATH.is_file():
        return {}
    try:
        payload = json.loads(OUTPUT_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}

    entries = payload.get("tickers", []) if isinstance(payload, dict) else []
    existing: dict[str, dict] = {}
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        _push(existing, entry.get("ticker", ""), entry.get("name", ""), entry.get("market", "US"))
    return existing


def build_ticker_catalog() -> tuple[dict[str, dict], list[str]]:
    combined = load_existing_catalog()
    warnings: list[str] = []

    fetchers = [
        ("nasdaq_listed", lambda payload: parse_pipe_symbol_file(payload, "Symbol", "Security Name", "US")),
        ("other_listed", lambda payload: parse_pipe_symbol_file(payload, "ACT Symbol", "Security Name", "US")),
        ("tsx_companies", lambda payload: parse_tmx_json(payload, "CA")),
        ("tsxv_companies", lambda payload: parse_tmx_json(payload, "CA")),
    ]

    for source_key, parser in fetchers:
        url = SOURCES[source_key]
        try:
            payload = fetch_text(url)
            parsed = parser(payload)
            for ticker, entry in parsed.items():
                _push(combined, ticker, entry.get("name", ""), entry.get("market", "US"))
        except Exception as exc:  # noqa: BLE001 - report and continue for partial builds.
            warnings.append(f"{source_key} failed: {exc}")

    return combined, warnings


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--fail-on-empty",
        action="store_true",
        help="Exit with non-zero status if no tickers are available after scraping.",
    )
    args = parser.parse_args()

    catalog, warnings = build_ticker_catalog()

    if not catalog and args.fail_on_empty:
        raise SystemExit("No tickers scraped and no existing catalog to preserve.")

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "source": "scraped",
        "ticker_count": len(catalog),
        "warnings": warnings,
        "tickers": sorted(catalog.values(), key=lambda item: item["ticker"]),
    }
    OUTPUT_PATH.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {len(catalog)} tickers to {OUTPUT_PATH}")
    if warnings:
        print("Warnings:")
        for warning in warnings:
            print(f"- {warning}")


if __name__ == "__main__":
    main()
