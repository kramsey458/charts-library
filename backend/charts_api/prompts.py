from __future__ import annotations

PROMPT_VERSION = "chart-analysis-v2"

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


CHECKLIST_VERDICT_PROMPT = (
    "This is a daily chart for HOOD. I want you to issue a determination for these factors. "
    "1. PANEL 1: Is the last colored candle red or yellow - im talking about panel 1, and not "
    "the volume bars. Yellow candle = downtrend, especially when followed by light blue candles. "
    "Red candle = uptrend, especially when followed by dark blue candles. Respond with either "
    '"red candle" or "yellow candle" ONLY 2. PANEL 2: Is the trend in panel 2 (jacky trend expert), '
    "bullish or bearish? (just give a verdict as either bullish or bearish). Respond with either "
    '"trend bullish" or "trend bearish" ONLY 3. PANEL 3: Is the red vertical bar in the panel 3 '
    "histogram increasing (consecutive light red = decreasing, consecutive dark red = increasing). "
    'Respond with either "Whale +" (there are consecutive dark red bars or "Whale -" (which means '
    'consecutive light red bars) 4. Panel 4: Is the MACD bar red or green? Respond with either "MACD +" '
    '(if green) or "MACD -" (if red) 5. Panel 4: Is the blue line under the orange line (MACD - cross aka '
    "bearish), or is the blue line ABOVE the orange line (MACD + cross aka bullish). Respond with either "
    '"MACD + cross" if the blue is above the orange line, and "MACD - cross" if the orange is below the '
    'blue 6. You may ignore the last panel "trend exhaustion"'
)
