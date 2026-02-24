from __future__ import annotations

import re
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


CHECKLIST_VERDICT_MAP = {
    "red candle": "red_candle",
    "yellow candle": "yellow_candle",
    "trend bullish": "trend_bullish",
    "trend bearish": "trend_bearish",
    "whale +": "whale_accumulation_plus",
    "whale -": "whale_accumulation_minus",
    "macd +": "macd_positive",
    "macd -": "macd_negative",
    "macd + cross": "macd_plus_cross",
    "macd - cross": "macd_minus_cross",
}

CHECKLIST_EXCLUSIVE_GROUPS = (
    {"red_candle", "yellow_candle"},
    {"trend_bullish", "trend_bearish"},
    {"whale_accumulation_plus", "whale_accumulation_minus"},
    {"macd_positive", "macd_negative"},
    {"macd_plus_cross", "macd_minus_cross"},
)


def normalize_verdict_line(raw_line: str) -> str:
    line = str(raw_line or "").strip().lower()
    line = re.sub(r'^[\-•\*\d\)\.\s]+', "", line)
    line = line.strip(' "\'')
    return line


def apply_checklist_verdicts(base_checklist: dict[str, bool], verdict_text: str) -> dict[str, bool]:
    checklist = sanitize_checklist(base_checklist)
    if not verdict_text:
        return checklist

    matched_keys: set[str] = set()
    for line in str(verdict_text).splitlines():
        key = CHECKLIST_VERDICT_MAP.get(normalize_verdict_line(line))
        if key:
            matched_keys.add(key)

    for group in CHECKLIST_EXCLUSIVE_GROUPS:
        selected = group.intersection(matched_keys)
        if not selected:
            continue
        selected_key = next(iter(selected))
        for key in group:
            checklist[key] = key == selected_key

    return checklist
