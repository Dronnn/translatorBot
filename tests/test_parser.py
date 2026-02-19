from bot.parser import ParseErrorCode, ParseMode, parse_message_text


def test_parse_explicit_pair() -> None:
    parsed = parse_message_text("de-ru: Hallo")
    assert parsed.ok
    assert parsed.mode == ParseMode.EXPLICIT_PAIR
    assert parsed.src == "de"
    assert parsed.dst == "ru"
    assert parsed.text == "Hallo"


def test_parse_explicit_pair_without_colon() -> None:
    parsed = parse_message_text("de-en Vater")
    assert parsed.ok
    assert parsed.mode == ParseMode.EXPLICIT_PAIR
    assert parsed.src == "de"
    assert parsed.dst == "en"
    assert parsed.text == "Vater"


def test_parse_auto_all_without_default_pair() -> None:
    parsed = parse_message_text("Freundschaft")
    assert parsed.ok
    assert parsed.mode == ParseMode.AUTO_ALL
    assert parsed.text == "Freundschaft"


def test_parse_uses_default_pair_when_prefix_absent() -> None:
    parsed = parse_message_text("Hello", default_pair=("en", "hy"))
    assert parsed.ok
    assert parsed.mode == ParseMode.DEFAULT_PAIR
    assert parsed.src == "en"
    assert parsed.dst == "hy"


def test_explicit_pair_has_priority_over_default_pair() -> None:
    parsed = parse_message_text("de-ru: Hallo", default_pair=("en", "hy"))
    assert parsed.ok
    assert parsed.mode == ParseMode.EXPLICIT_PAIR
    assert parsed.src == "de"
    assert parsed.dst == "ru"
    assert parsed.text == "Hallo"


def test_parse_invalid_pair_prefix() -> None:
    parsed = parse_message_text("xx-yy: text")
    assert not parsed.ok
    assert parsed.error == ParseErrorCode.INVALID_PAIR


def test_parse_empty_message() -> None:
    parsed = parse_message_text("   ")
    assert not parsed.ok
    assert parsed.error == ParseErrorCode.EMPTY


def test_parse_too_long_message() -> None:
    parsed = parse_message_text("a" * 501)
    assert not parsed.ok
    assert parsed.error == ParseErrorCode.TOO_LONG
