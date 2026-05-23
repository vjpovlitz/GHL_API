"""Sanitizer regression tests. If any of these fail, BULK INSERT will too."""
from __future__ import annotations

from ghl_api.sanitize import (
    clean_bit,
    clean_date,
    clean_email,
    clean_id,
    clean_int,
    clean_phone,
    clean_text,
    clean_utc_ts,
)


# ---- clean_text: the SQL-Server safety contract ----

def test_clean_text_strips_newlines_crlf_and_lf():
    assert clean_text("hello\r\nworld") == "hello world"
    assert clean_text("a\nb\nc") == "a b c"
    assert clean_text("a\rb") == "a b"


def test_clean_text_strips_tabs():
    assert clean_text("a\tb\tc") == "a b c"


def test_clean_text_drops_null_bytes_and_c0_controls():
    assert clean_text("a\x00b") == "ab"
    assert clean_text("a\x01\x02b") == "ab"


def test_clean_text_keeps_space_and_high_unicode():
    assert clean_text("hello world") == "hello world"
    assert clean_text("café — 🎉") == "café — 🎉"  # emoji + em-dash preserved


def test_clean_text_collapses_internal_whitespace_and_trims():
    assert clean_text("  a   b\n\nc  ") == "a b c"


def test_clean_text_missing_tokens_become_empty():
    for tok in ["None", "null", "NaN", "undefined", "  NULL  "]:
        assert clean_text(tok) == ""


def test_clean_text_none_and_empty():
    assert clean_text(None) == ""
    assert clean_text("") == ""


def test_clean_text_lists_become_pipe_delimited():
    assert clean_text(["a", "b", "c"]) == "a|b|c"
    assert clean_text(["a", None, "", "b"]) == "a|b"


def test_clean_text_dict_becomes_compact_json():
    out = clean_text({"x": 1, "y": "z"})
    assert out == '{"x":1,"y":"z"}'


def test_clean_text_truncates_to_max_len():
    assert clean_text("a" * 50, max_len=10) == "a" * 10


def test_clean_text_handles_mixed_corruption():
    """The exact failure mode from the original Conversations.csv bug."""
    raw = "Hello,\r\nthis has\ta tab\x00 and a null"
    assert clean_text(raw) == "Hello, this has a tab and a null"
    assert "\n" not in clean_text(raw)
    assert "\r" not in clean_text(raw)
    assert "\t" not in clean_text(raw)
    assert "\x00" not in clean_text(raw)


# ---- clean_id ----

def test_clean_id_keeps_alnum_dash_underscore():
    assert clean_id("abc123") == "abc123"
    assert clean_id("abc-123_xyz") == "abc-123_xyz"
    assert clean_id("abc 123") == "abc123"
    assert clean_id("abc'\"123") == "abc123"


# ---- clean_phone ----

def test_clean_phone_e164_passthrough():
    assert clean_phone("+12025551234") == "+12025551234"


def test_clean_phone_strips_formatting():
    assert clean_phone("+1 (202) 555-1234") == "+12025551234"


def test_clean_phone_empty():
    assert clean_phone(None) == ""
    assert clean_phone("") == ""


# ---- clean_bit ----

def test_clean_bit_true_false_unknown():
    assert clean_bit(True) == "1"
    assert clean_bit(False) == "0"
    assert clean_bit(None) == ""
    assert clean_bit("") == ""
    assert clean_bit("true") == "1"
    assert clean_bit("False") == "0"
    assert clean_bit("yes") == "1"
    assert clean_bit("no") == "0"


# ---- clean_int ----

def test_clean_int_basic():
    assert clean_int(42) == "42"
    assert clean_int("42") == "42"
    assert clean_int("42.0") == "42"
    assert clean_int(None) == ""
    assert clean_int("not a number") == ""


# ---- clean_utc_ts ----

def test_clean_utc_ts_iso():
    assert clean_utc_ts("2026-05-23T03:01:24.444Z") == "2026-05-23T03:01:24.444Z"


def test_clean_utc_ts_epoch_ms():
    # GHL Conversations endpoint returns this format
    assert clean_utc_ts(1779500080557) == "2026-05-23T01:34:40.000Z"
    assert clean_utc_ts("1779500080557") == "2026-05-23T01:34:40.000Z"


def test_clean_utc_ts_epoch_seconds():
    assert clean_utc_ts(1779500080) == "2026-05-23T01:34:40.000Z"


def test_clean_utc_ts_empty_and_bad():
    assert clean_utc_ts(None) == ""
    assert clean_utc_ts("") == ""
    assert clean_utc_ts("not a date") == ""


# ---- clean_date ----

def test_clean_date_basic():
    assert clean_date("2026-05-23T03:01:24Z") == "2026-05-23"
    assert clean_date("2026-05-23") == "2026-05-23"
    assert clean_date("") == ""
    assert clean_date(None) == ""


# ---- clean_email ----

def test_clean_email_basic():
    assert clean_email("  Alice@Example.COM ") == "alice@example.com"
    assert clean_email(None) == ""
    # If no '@', return original cleaned (will fail validation downstream)
    assert clean_email("not-an-email") == "not-an-email"
