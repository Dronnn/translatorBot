from bot.handlers import (
    INVALID_PAIR_MESSAGE,
    TOO_LONG_MESSAGE,
    format_translation_response,
    parse_error_message,
)
from bot.parser import ParseErrorCode, ParseMode
from bot.translator import TranslationResult, TranslationStatus


def test_parse_error_message_mappings() -> None:
    assert parse_error_message(ParseErrorCode.TOO_LONG) == TOO_LONG_MESSAGE
    assert parse_error_message(ParseErrorCode.INVALID_PAIR) == INVALID_PAIR_MESSAGE
    assert parse_error_message(ParseErrorCode.EMPTY) is None


def test_format_translation_response_explicit_pair() -> None:
    result = TranslationResult(
        status=TranslationStatus.OK,
        source_language="de",
        translations={"ru": "привет"},
    )
    assert format_translation_response(result, ParseMode.EXPLICIT_PAIR) == "- Русский: привет"


def test_format_translation_response_auto_all() -> None:
    result = TranslationResult(
        status=TranslationStatus.OK,
        source_language="de",
        translations={
            "ru": "дружба",
            "en": "friendship",
            "hy": "բարեկամություն",
        },
    )
    formatted = format_translation_response(result, ParseMode.AUTO_ALL)
    assert "Исходный язык: Deutsch" in formatted
    assert "- Русский: дружба" in formatted
    assert "- English: friendship" in formatted
    assert "- Հայերեն: բարեկամություն" in formatted


def test_format_translation_response_includes_german_governance() -> None:
    result = TranslationResult(
        status=TranslationStatus.OK,
        source_language="ru",
        translations={"de": "teilnehmen"},
        german_verb_governance="teilnehmen an + D",
    )
    formatted = format_translation_response(result, ParseMode.EXPLICIT_PAIR)
    assert "- Deutsch: teilnehmen" in formatted
    assert "Управление (de): teilnehmen an + D" in formatted


def test_format_translation_response_includes_past_forms_line() -> None:
    result = TranslationResult(
        status=TranslationStatus.OK,
        source_language="de",
        translations={"ru": "участвовать"},
        verb_past_forms_line=(
            "DE: Perfekt: hat teilgenommen; Prateritum: nahm teil | "
            "EN: Past Simple: participated; Past Participle: participated | "
            "RU: участвовал/участвовала | HY: մասնակցեց"
        ),
    )
    formatted = format_translation_response(result, ParseMode.EXPLICIT_PAIR)
    assert "Прошедшие формы:" in formatted
    assert "Prateritum: nahm teil" in formatted


def test_format_translation_response_includes_german_noun_article_line() -> None:
    result = TranslationResult(
        status=TranslationStatus.OK,
        source_language="en",
        translations={"de": "Pappe"},
        german_noun_article_line="die Pappe (f.)",
    )
    formatted = format_translation_response(result, ParseMode.EXPLICIT_PAIR)
    assert "Артикль/род (de): die Pappe (f.)" in formatted
