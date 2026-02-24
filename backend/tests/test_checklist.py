from charts_api.checklist import (
    CHECKLIST_KEYS,
    empty_checklist,
    encode_checklist_context,
    parse_bool,
    parse_checklist_context,
    sanitize_checklist,
    apply_checklist_verdicts,
)


def test_parse_bool_variants():
    assert parse_bool("true")
    assert parse_bool("1")
    assert parse_bool("YES")
    assert not parse_bool("false")
    assert not parse_bool(None)


def test_sanitize_checklist_only_known_keys():
    payload = {
        "red_candle": "true",
        "trend_bullish": "yes",
        "yellow_candle": "on",
        "whale_accumulation_plus": "1",
        "unknown": True,
    }
    checklist = sanitize_checklist(payload)

    assert checklist["red_candle"] is True
    assert checklist["trend_bullish"] is True
    assert checklist["yellow_candle"] is True
    assert checklist["whale_accumulation_plus"] is True
    assert checklist["macd_negative"] is False
    assert set(checklist.keys()) == set(CHECKLIST_KEYS)


def test_checklist_context_roundtrip():
    checklist = empty_checklist()
    checklist["red_candle"] = True
    checklist["yellow_candle"] = True
    checklist["macd_positive"] = True

    encoded = encode_checklist_context(checklist)
    decoded = parse_checklist_context(encoded)

    assert decoded == checklist


def test_apply_checklist_verdicts_sets_expected_flags():
    verdicts = "\n".join([
        "yellow candle",
        "trend bearish",
        "Whale +",
        "MACD -",
        "MACD - cross",
    ])

    checklist = apply_checklist_verdicts(empty_checklist(), verdicts)

    assert checklist["yellow_candle"] is True
    assert checklist["red_candle"] is False
    assert checklist["trend_bearish"] is True
    assert checklist["trend_bullish"] is False
    assert checklist["whale_accumulation_plus"] is True
    assert checklist["whale_accumulation_minus"] is False
    assert checklist["macd_negative"] is True
    assert checklist["macd_positive"] is False
    assert checklist["macd_minus_cross"] is True
    assert checklist["macd_plus_cross"] is False
