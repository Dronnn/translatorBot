from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional

from bot.lang_codes import normalize_lang_code, normalize_pair

MAX_INPUT_LENGTH = 500


class ParseMode(str, Enum):
    EXPLICIT_PAIR = "explicit_pair"
    FORCED_SOURCE_ALL = "forced_source_all"
    DEFAULT_PAIR = "default_pair"
    AUTO_ALL = "auto_all"


class ParseErrorCode(str, Enum):
    EMPTY = "empty"
    TOO_LONG = "too_long"
    INVALID_PAIR = "invalid_pair"


@dataclass(frozen=True)
class ParsedInput:
    mode: Optional[ParseMode] = None
    text: str = ""
    src: str | None = None
    dst: str | None = None
    error: ParseErrorCode | None = None

    @property
    def ok(self) -> bool:
        return self.error is None and self.mode is not None


def _looks_like_pair_prefix(prefix: str) -> bool:
    compact = prefix.strip()
    if not compact:
        return False
    if any(delimiter in compact for delimiter in ("-", "_", "→")):
        return True
    parts = compact.split()
    return len(parts) == 2


def _validate_text_length(text: str) -> ParseErrorCode | None:
    if not text:
        return ParseErrorCode.EMPTY
    if len(text) > MAX_INPUT_LENGTH:
        return ParseErrorCode.TOO_LONG
    return None


def parse_message_text(
    raw_text: str | None,
    default_pair: tuple[str, str] | None = None,
) -> ParsedInput:
    """Parse user text into translation request mode."""
    text = (raw_text or "").strip()
    if not text:
        return ParsedInput(error=ParseErrorCode.EMPTY)

    explicit_pair: tuple[str, str] | None = None
    forced_source: str | None = None
    candidate_text = text

    # Support explicit pair without colon: `de-en Hallo`
    # (kept strict to tokenized delimiters to avoid over-matching plain text).
    if ":" not in text:
        parts = text.split(maxsplit=1)
        if len(parts) == 2:
            maybe_pair = normalize_pair(parts[0])
            if maybe_pair:
                explicit_pair = maybe_pair
                candidate_text = parts[1].strip()
            else:
                maybe_source = normalize_lang_code(parts[0])
                if maybe_source:
                    forced_source = maybe_source
                    candidate_text = parts[1].strip()

    if ":" in text:
        prefix, remainder = text.split(":", 1)
        maybe_pair = normalize_pair(prefix)
        if maybe_pair:
            explicit_pair = maybe_pair
            candidate_text = remainder.strip()
        elif maybe_source := normalize_lang_code(prefix):
            forced_source = maybe_source
            candidate_text = remainder.strip()
        else:
            if _looks_like_pair_prefix(prefix):
                return ParsedInput(error=ParseErrorCode.INVALID_PAIR)

    length_error = _validate_text_length(candidate_text)
    if length_error:
        return ParsedInput(error=length_error)

    if explicit_pair:
        src, dst = explicit_pair
        return ParsedInput(
            mode=ParseMode.EXPLICIT_PAIR,
            text=candidate_text,
            src=src,
            dst=dst,
        )

    if forced_source:
        return ParsedInput(
            mode=ParseMode.FORCED_SOURCE_ALL,
            text=candidate_text,
            src=forced_source,
        )

    if default_pair:
        src, dst = default_pair
        return ParsedInput(
            mode=ParseMode.DEFAULT_PAIR,
            text=candidate_text,
            src=src,
            dst=dst,
        )

    return ParsedInput(mode=ParseMode.AUTO_ALL, text=candidate_text)
