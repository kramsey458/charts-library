from __future__ import annotations

PROMPT_VERSION = "chart-analysis-v1"

SYSTEM_PROMPT = (
    "You are a senior technical trading analyst. Analyze the provided chart image and provide concise, "
    "actionable notes. Avoid giving financial advice certainty guarantees."
)


def build_chart_analysis_prompt(ticker: str, date_label: str, filename: str) -> str:
    return (
        "Analyze this trading chart image and return a structured plain-text response with these sections:\n"
        "1) Trend summary\n"
        "2) Support and resistance zones\n"
        "3) Momentum/volume clues visible on chart\n"
        "4) Risk notes (invalidations)\n"
        "5) One-sentence watchlist plan\n\n"
        f"Ticker: {ticker}\n"
        f"Date label: {date_label}\n"
        f"Filename: {filename}\n"
    )
