from charts_api.checklist import (
    CHECKLIST_KEYS,
    empty_checklist,
    encode_checklist_context,
    parse_bool,
    parse_checklist_context,
    sanitize_checklist,
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
        "unknown": True,
    }
    checklist = sanitize_checklist(payload)

    assert checklist["red_candle"] is True
    assert checklist["trend_bullish"] is True
    assert checklist["whale_over_50"] is False
    assert set(checklist.keys()) == set(CHECKLIST_KEYS)


def test_checklist_context_roundtrip():
    checklist = empty_checklist()
    checklist["red_candle"] = True
    checklist["momentum_green"] = True

    encoded = encode_checklist_context(checklist)
    decoded = parse_checklist_context(encoded)

    assert decoded == checklist
