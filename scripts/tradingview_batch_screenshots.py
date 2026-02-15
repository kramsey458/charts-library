#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

from backend.charts_api.pipeline.tradingview_runner import run_capture


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Batch-save TradingView chart images.")
    source_group = parser.add_mutually_exclusive_group(required=True)
    source_group.add_argument("--tickers", help="Comma-separated tickers")
    source_group.add_argument("--tickers-file", help="File with one ticker per line")
    parser.add_argument("--output-dir", default="downloads")
    parser.add_argument("--headless", action="store_true")
    return parser.parse_args()


def load_tickers(args: argparse.Namespace) -> list[str]:
    if args.tickers:
        return [token.strip().upper() for token in args.tickers.split(",") if token.strip()]
    lines = Path(args.tickers_file).read_text(encoding="utf-8").splitlines()
    return [line.strip().upper() for line in lines if line.strip() and not line.strip().startswith("#")]


def main() -> int:
    args = parse_args()
    tickers = load_tickers(args)
    result = run_capture(
        tickers=tickers,
        output_dir=Path(args.output_dir),
        launch_url="https://www.tradingview.com/chart/",
        run_options={"headless": args.headless, "mock_mode": False},
    )
    for item in result["results"]:
        print(item)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
