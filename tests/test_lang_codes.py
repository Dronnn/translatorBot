import pytest

from bot.lang_codes import normalize_lang_code, normalize_pair


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("ru", "ru"),
        ("русский", "ru"),
        ("russian", "ru"),
        ("en", "en"),
        ("англ", "en"),
        ("english", "en"),
        ("de", "de"),
        ("немецкий", "de"),
        ("deutsch", "de"),
        ("hy", "hy"),
        ("հայերեն", "hy"),
        ("армянский", "hy"),
    ],
)
def test_normalize_lang_code(raw: str, expected: str) -> None:
    assert normalize_lang_code(raw) == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("ru-en", ("ru", "en")),
        ("ru_en", ("ru", "en")),
        ("ru→en", ("ru", "en")),
        ("ru en", ("ru", "en")),
        ("русский-английский", ("ru", "en")),
        ("de hy", ("de", "hy")),
    ],
)
def test_normalize_pair_valid(raw: str, expected: tuple[str, str]) -> None:
    assert normalize_pair(raw) == expected


@pytest.mark.parametrize("raw", ["", "ru", "xx-en", "ru-xx", "ru-ru", "xx yy"])
def test_normalize_pair_invalid(raw: str) -> None:
    assert normalize_pair(raw) is None
