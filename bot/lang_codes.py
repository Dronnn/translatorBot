from __future__ import annotations

import re
from typing import Optional

SUPPORTED_LANGUAGES: tuple[str, str, str, str] = ("ru", "en", "de", "hy")

LANGUAGE_LABELS: dict[str, str] = {
    "ru": "Русский",
    "en": "English",
    "de": "Deutsch",
    "hy": "Հայերեն",
}

# Accept language aliases in Latin, Cyrillic, and Armenian scripts.
LANGUAGE_ALIASES: dict[str, str] = {
    # Russian
    "ru": "ru",
    "rus": "ru",
    "russian": "ru",
    "рус": "ru",
    "русский": "ru",
    "русском": "ru",
    "ռուս": "ru",
    "ռուսերեն": "ru",
    # English
    "en": "en",
    "eng": "en",
    "english": "en",
    "анг": "en",
    "англ": "en",
    "английский": "en",
    "անգլ": "en",
    "անգլերեն": "en",
    # German
    "de": "de",
    "deu": "de",
    "ger": "de",
    "german": "de",
    "deutsch": "de",
    "нем": "de",
    "немецкий": "de",
    "գերմ": "de",
    "գերմաներեն": "de",
    # Armenian
    "hy": "hy",
    "hye": "hy",
    "arm": "hy",
    "armenian": "hy",
    "арм": "hy",
    "армянский": "hy",
    "հայ": "hy",
    "հայերեն": "hy",
}

_PAIR_PATTERN = re.compile(r"^(.+?)\s*(?:-|_|→|\s)\s*(.+?)$")


def _clean_language_token(raw: str) -> str:
    token = raw.strip().lower()
    token = token.replace("ё", "е")
    token = re.sub(r"[^0-9a-zа-яա-ֆ]+", "", token)
    return token


def normalize_lang_code(raw: str | None) -> Optional[str]:
    """Normalize a user-provided language alias to canonical ISO code."""
    if raw is None:
        return None
    cleaned = _clean_language_token(raw)
    if not cleaned:
        return None
    if cleaned in SUPPORTED_LANGUAGES:
        return cleaned
    return LANGUAGE_ALIASES.get(cleaned)


def normalize_pair(raw: str | None) -> Optional[tuple[str, str]]:
    """
    Normalize language pair aliases (for example `ru-en`, `ru→en`, `ru en`).

    Returns `(src, dst)` when both languages are supported and different,
    otherwise returns `None`.
    """
    if raw is None:
        return None

    text = raw.strip()
    if not text:
        return None

    match = _PAIR_PATTERN.match(text)
    if not match:
        return None

    src_raw, dst_raw = match.group(1), match.group(2)
    src = normalize_lang_code(src_raw)
    dst = normalize_lang_code(dst_raw)

    if not src or not dst or src == dst:
        return None
    return src, dst


def is_supported_language(code: str | None) -> bool:
    return bool(code and code in SUPPORTED_LANGUAGES)


def language_label(code: str) -> str:
    return LANGUAGE_LABELS.get(code, code)
