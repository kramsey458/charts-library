from __future__ import annotations

from typing import Any
from urllib.parse import quote, unquote

CHECKLIST_KEYS = [
    "red_candle",
    "trend_bullish",
    "whale_accumulation_plus",
    "macd_positive",
    "macd_plus_cross",
    "yellow_candle",
    "trend_bearish",
    "whale_accumulation_minus",
    "macd_negative",
    "macd_minus_cross",
]


def parse_bool(value: Any) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def empty_checklist() -> dict[str, bool]:
    return {key: False for key in CHECKLIST_KEYS}


def sanitize_checklist(payload: dict[str, Any] | None) -> dict[str, bool]:
    checklist = empty_checklist()
    if not payload:
        return checklist

    for key in CHECKLIST_KEYS:
        checklist[key] = parse_bool(payload.get(key, False))
    return checklist


def encode_checklist_context(checklist: dict[str, bool]) -> str:
    enabled_keys = [key for key in CHECKLIST_KEYS if checklist.get(key, False)]
    return quote(",".join(enabled_keys), safe=",")


def parse_checklist_context(raw_value: Any) -> dict[str, bool]:
    try:
        decoded = unquote(str(raw_value or ""))
    except Exception:
        decoded = str(raw_value or "")

    selected_keys = {item.strip() for item in decoded.split(",") if item.strip()}
    checklist = empty_checklist()
    for key in CHECKLIST_KEYS:
        checklist[key] = key in selected_keys
    return checklist
