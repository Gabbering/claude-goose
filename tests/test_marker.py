"""Unit tests for the marker module.

Run with:  python -m pytest tests/ -q
"""

from __future__ import annotations

from src import marker


def test_parse_none_when_absent() -> None:
    assert marker.parse("no marker here at all") is None
    assert marker.parse("") is None


def test_parse_basic() -> None:
    body = "## findings\n\nsome stuff\n\n<!-- ga-bot:v1 sha=abc1234 -->"
    m = marker.parse(body)
    assert m is not None
    assert m.sha == "abc1234"
    assert m.silent_skips == []
    assert m.raw == "<!-- ga-bot:v1 sha=abc1234 -->"


def test_parse_with_silent_skips() -> None:
    body = "<!-- ga-bot:v1 sha=deadbee silent_skips=111aaaa,222bbbb -->"
    m = marker.parse(body)
    assert m is not None
    assert m.sha == "deadbee"
    assert m.silent_skips == ["111aaaa", "222bbbb"]


def test_parse_is_case_insensitive_on_sha() -> None:
    body = "<!-- ga-bot:v1 sha=ABC1234 -->"
    m = marker.parse(body)
    assert m is not None
    assert m.sha == "abc1234"


def test_parse_first_marker_wins() -> None:
    body = "<!-- ga-bot:v1 sha=aaaaaaa -->\n\nlater:\n<!-- ga-bot:v1 sha=bbbbbbb -->"
    m = marker.parse(body)
    assert m is not None
    assert m.sha == "aaaaaaa"


def test_encode_basic() -> None:
    s = marker.encode("abc1234")
    assert s == "<!-- ga-bot:v1 sha=abc1234 -->"


def test_encode_with_skips_dedup_and_lowercase() -> None:
    s = marker.encode("ABC1234", silent_skips=["AAA", "bbb", "aaa"])
    assert s == "<!-- ga-bot:v1 sha=abc1234 silent_skips=aaa,bbb -->"


def test_encode_empty_skips_list_omitted() -> None:
    s = marker.encode("abc", silent_skips=[])
    assert "silent_skips" not in s


def test_replace_in_body_swaps_existing() -> None:
    body = "hello\n<!-- ga-bot:v1 sha=01d1111 -->"
    new_marker = "<!-- ga-bot:v1 sha=ae22222 -->"
    result = marker.replace_in_body(body, new_marker)
    assert "sha=01d1111" not in result
    assert "sha=ae22222" in result
    assert result.startswith("hello")


def test_replace_in_body_appends_when_absent() -> None:
    body = "hello world"
    new_marker = "<!-- ga-bot:v1 sha=abc -->"
    result = marker.replace_in_body(body, new_marker)
    assert result.startswith("hello world")
    assert result.endswith(new_marker)


def test_roundtrip_through_replace_preserves_skips() -> None:
    # Start with a marker, replace it, parse the result — should see the new sha
    # and the new skips.
    body = "review text\n\n<!-- ga-bot:v1 sha=01dbeef -->"
    replacement = marker.encode("abc1234", silent_skips=["01dbeef"])
    new_body = marker.replace_in_body(body, replacement)
    m = marker.parse(new_body)
    assert m is not None
    assert m.sha == "abc1234"
    assert m.silent_skips == ["01dbeef"]
