from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from typing import Dict, List, Literal, Union

from openai import AsyncOpenAI
from pydantic import BaseModel, ValidationError

from bot.lang_codes import SUPPORTED_LANGUAGES

logger = logging.getLogger(__name__)


SYSTEM_PROMPT = (
    "You are a translation engine for ru, en, de, hy. "
    "Return only strict JSON with keys detected_language and translations. "
    "Do not include markdown. Do not include extra keys. "
    "detected_language must be one of ru,en,de,hy,unknown. "
    "Translate directly without stylistic rewriting. "
    "For single words, include up to 3 common variants only when genuinely common."
)

GERMAN_VERB_GOVERNANCE_SYSTEM_PROMPT = (
    "You are a German grammar helper. "
    "Return strict JSON with keys is_verb and governance. "
    "If the input is not a German verb, return {\"is_verb\": false, \"governance\": \"\"}. "
    "If it is a verb, return only one common government pattern in this format: "
    "\"verb preposition + CASE\", where CASE is one of A, D, G. "
    "Examples: \"teilnehmen an + D\", \"warten auf + A\", \"sich erinnern an + A\". "
    "No extra text."
)

GERMAN_NOUN_ARTICLE_SYSTEM_PROMPT = (
    "You are a German grammar helper for nouns. "
    "Return strict JSON with keys is_noun, noun, article, gender. "
    "If the input is not a German noun, return "
    "{\"is_noun\": false, \"noun\": \"\", \"article\": \"\", \"gender\": \"\"}. "
    "If it is a noun, return lemma in singular with capitalization in noun, "
    "article must be one of der/die/das, gender must be one of m/f/n. "
    "No extra text."
)

VERB_FORMS_SYSTEM_PROMPT = (
    "You are a multilingual verb morphology helper for ru, en, de, hy. "
    "Return strict JSON with keys: is_verb, infinitives, past_lookup, past_display. "
    "If input is not a verb, return is_verb=false and keep objects empty. "
    "If it is a verb, return infinitives for all four languages. "
    "past_lookup must contain keys ru_past, en_past_simple, en_past_participle, "
    "de_perfekt, de_prateritum, hy_past with plain forms only (no labels). "
    "past_display must contain keys ru,en,de,hy with concise human-readable past forms. "
    "For German include exactly two forms in past_display.de: Perfekt and Prateritum. "
    "For English include exactly two forms in past_display.en: Past Simple and Past Participle. "
    "No markdown and no extra keys."
)

_VERB_PAST_LOOKUP_KEYS: tuple[str, ...] = (
    "ru_past",
    "en_past_simple",
    "en_past_participle",
    "de_perfekt",
    "de_prateritum",
    "hy_past",
)


class OpenAITranslationSchema(BaseModel):
    detected_language: Literal["ru", "en", "de", "hy", "unknown"]
    translations: Dict[str, Union[str, List[str]]]


class GermanVerbGovernanceSchema(BaseModel):
    is_verb: bool
    governance: str


class GermanNounArticleSchema(BaseModel):
    is_noun: bool
    noun: str
    article: str
    gender: str


class OpenAIVerbFormsSchema(BaseModel):
    is_verb: bool
    infinitives: Dict[str, str]
    past_lookup: Dict[str, str]
    past_display: Dict[str, str]


@dataclass(frozen=True)
class OpenAITranslationResult:
    detected_language: str
    translations: dict[str, str]


@dataclass(frozen=True)
class OpenAIVerbFormsResult:
    is_verb: bool
    infinitives: dict[str, str]
    past_lookup: dict[str, str]
    past_display: dict[str, str]


class OpenAITranslationClient:
    def __init__(
        self,
        api_key: str,
        model: str,
        timeout_seconds: float,
        max_retries: int,
    ) -> None:
        self._client = AsyncOpenAI(api_key=api_key)
        self._model = model
        self._timeout_seconds = timeout_seconds
        self._max_retries = max_retries

    async def translate(
        self,
        *,
        text: str,
        requested_targets: list[str],
        forced_source: str | None,
        allowed_languages: list[str] | None = None,
    ) -> OpenAITranslationResult:
        scope = allowed_languages or list(SUPPORTED_LANGUAGES)
        payload = {
            "input_text": text,
            "allowed_languages": scope,
            "requested_targets": requested_targets,
            "forced_source": forced_source,
            "requirements": {
                "translation_style": "direct",
                "max_variants_for_single_words": 3,
                "empty_translation_for_missing": False,
            },
        }

        last_error: Exception | None = None
        attempts = self._max_retries + 1

        for attempt in range(1, attempts + 1):
            try:
                completion = await self._client.chat.completions.create(
                    model=self._model,
                    temperature=0,
                    timeout=self._timeout_seconds,
                    response_format={"type": "json_object"},
                    messages=[
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {
                            "role": "user",
                            "content": (
                                "Return valid JSON for this request: "
                                f"{json.dumps(payload, ensure_ascii=False)}"
                            ),
                        },
                    ],
                )

                raw_content = completion.choices[0].message.content or "{}"
                parsed_json = json.loads(raw_content)
                validated = OpenAITranslationSchema.model_validate(parsed_json)

                filtered_translations: dict[str, str] = {}
                for lang in requested_targets:
                    raw_value = validated.translations.get(lang, "")
                    value = self._normalize_translation_value(raw_value)
                    if value:
                        filtered_translations[lang] = value

                return OpenAITranslationResult(
                    detected_language=validated.detected_language,
                    translations=filtered_translations,
                )
            except (json.JSONDecodeError, ValidationError, IndexError) as exc:
                last_error = exc
                logger.warning(
                    "Invalid OpenAI response schema on attempt %s/%s",
                    attempt,
                    attempts,
                )
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                logger.warning(
                    "OpenAI request failed on attempt %s/%s: %s",
                    attempt,
                    attempts,
                    exc.__class__.__name__,
                )

            if attempt < attempts:
                await asyncio.sleep(0.5 * attempt)

        raise RuntimeError("OpenAI translation request failed.") from last_error

    async def german_verb_governance(self, *, german_text: str) -> str | None:
        text = german_text.strip()
        if not text:
            return None

        payload = {
            "german_text": text,
            "format": "verb preposition + CASE",
            "allowed_cases": ["A", "D", "G"],
        }

        last_error: Exception | None = None
        attempts = self._max_retries + 1

        for attempt in range(1, attempts + 1):
            try:
                completion = await self._client.chat.completions.create(
                    model=self._model,
                    temperature=0,
                    timeout=self._timeout_seconds,
                    response_format={"type": "json_object"},
                    messages=[
                        {"role": "system", "content": GERMAN_VERB_GOVERNANCE_SYSTEM_PROMPT},
                        {
                            "role": "user",
                            "content": (
                                "Return valid JSON for this request: "
                                f"{json.dumps(payload, ensure_ascii=False)}"
                            ),
                        },
                    ],
                )

                raw_content = completion.choices[0].message.content or "{}"
                parsed_json = json.loads(raw_content)
                validated = GermanVerbGovernanceSchema.model_validate(parsed_json)

                governance = validated.governance.strip()
                if not validated.is_verb or not governance:
                    return None
                return governance
            except (json.JSONDecodeError, ValidationError, IndexError) as exc:
                last_error = exc
                logger.warning(
                    "Invalid German governance schema on attempt %s/%s",
                    attempt,
                    attempts,
                )
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                logger.warning(
                    "German governance request failed on attempt %s/%s: %s",
                    attempt,
                    attempts,
                    exc.__class__.__name__,
                )

            if attempt < attempts:
                await asyncio.sleep(0.5 * attempt)

        raise RuntimeError("OpenAI german governance request failed.") from last_error

    async def german_noun_article(self, *, german_text: str) -> str | None:
        text = german_text.strip()
        if not text:
            return None

        payload = {
            "german_text": text,
            "output": "article + noun + gender",
            "allowed_articles": ["der", "die", "das"],
            "allowed_gender": ["m", "f", "n"],
        }

        last_error: Exception | None = None
        attempts = self._max_retries + 1

        for attempt in range(1, attempts + 1):
            try:
                completion = await self._client.chat.completions.create(
                    model=self._model,
                    temperature=0,
                    timeout=self._timeout_seconds,
                    response_format={"type": "json_object"},
                    messages=[
                        {"role": "system", "content": GERMAN_NOUN_ARTICLE_SYSTEM_PROMPT},
                        {
                            "role": "user",
                            "content": (
                                "Return valid JSON for this request: "
                                f"{json.dumps(payload, ensure_ascii=False)}"
                            ),
                        },
                    ],
                )

                raw_content = completion.choices[0].message.content or "{}"
                parsed_json = json.loads(raw_content)
                validated = GermanNounArticleSchema.model_validate(parsed_json)

                if not validated.is_noun:
                    return None

                article = validated.article.strip().lower()
                noun = validated.noun.strip()
                gender = validated.gender.strip().lower()
                if article not in {"der", "die", "das"}:
                    return None
                if gender not in {"m", "f", "n"}:
                    return None
                if not noun:
                    return None

                noun = noun[:1].upper() + noun[1:]
                return f"{article} {noun} ({gender}.)"
            except (json.JSONDecodeError, ValidationError, IndexError) as exc:
                last_error = exc
                logger.warning(
                    "Invalid German noun schema on attempt %s/%s",
                    attempt,
                    attempts,
                )
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                logger.warning(
                    "German noun request failed on attempt %s/%s: %s",
                    attempt,
                    attempts,
                    exc.__class__.__name__,
                )

            if attempt < attempts:
                await asyncio.sleep(0.5 * attempt)

        raise RuntimeError("OpenAI german noun request failed.") from last_error

    async def verb_forms(
        self,
        *,
        source_language: str,
        source_text: str,
        known_translations: dict[str, str],
    ) -> OpenAIVerbFormsResult:
        text = source_text.strip()
        if not text:
            return OpenAIVerbFormsResult(
                is_verb=False,
                infinitives={},
                past_lookup={},
                past_display={},
            )

        payload = {
            "source_language": source_language,
            "source_text": text,
            "known_translations": known_translations,
            "requirements": {
                "supported_languages": list(SUPPORTED_LANGUAGES),
                "infinitives_required_for_all_languages": True,
                "past_lookup_keys": list(_VERB_PAST_LOOKUP_KEYS),
                "de_past_forms_required": ["Perfekt", "Prateritum"],
                "en_past_forms_required": ["Past Simple", "Past Participle"],
            },
        }

        last_error: Exception | None = None
        attempts = self._max_retries + 1

        for attempt in range(1, attempts + 1):
            try:
                completion = await self._client.chat.completions.create(
                    model=self._model,
                    temperature=0,
                    timeout=self._timeout_seconds,
                    response_format={"type": "json_object"},
                    messages=[
                        {"role": "system", "content": VERB_FORMS_SYSTEM_PROMPT},
                        {
                            "role": "user",
                            "content": (
                                "Return valid JSON for this request: "
                                f"{json.dumps(payload, ensure_ascii=False)}"
                            ),
                        },
                    ],
                )

                raw_content = completion.choices[0].message.content or "{}"
                parsed_json = json.loads(raw_content)
                validated = OpenAIVerbFormsSchema.model_validate(parsed_json)

                if not validated.is_verb:
                    return OpenAIVerbFormsResult(
                        is_verb=False,
                        infinitives={},
                        past_lookup={},
                        past_display={},
                    )

                infinitives = {
                    lang: str(validated.infinitives.get(lang, "")).strip()
                    for lang in SUPPORTED_LANGUAGES
                }
                past_lookup = {
                    key: str(validated.past_lookup.get(key, "")).strip()
                    for key in _VERB_PAST_LOOKUP_KEYS
                }
                past_display = {
                    lang: str(validated.past_display.get(lang, "")).strip()
                    for lang in SUPPORTED_LANGUAGES
                }

                if any(not infinitives[lang] for lang in SUPPORTED_LANGUAGES):
                    return OpenAIVerbFormsResult(
                        is_verb=False,
                        infinitives={},
                        past_lookup={},
                        past_display={},
                    )
                if any(not past_lookup[key] for key in _VERB_PAST_LOOKUP_KEYS):
                    return OpenAIVerbFormsResult(
                        is_verb=False,
                        infinitives={},
                        past_lookup={},
                        past_display={},
                    )
                if any(not past_display[lang] for lang in SUPPORTED_LANGUAGES):
                    return OpenAIVerbFormsResult(
                        is_verb=False,
                        infinitives={},
                        past_lookup={},
                        past_display={},
                    )

                return OpenAIVerbFormsResult(
                    is_verb=True,
                    infinitives=infinitives,
                    past_lookup=past_lookup,
                    past_display=past_display,
                )
            except (json.JSONDecodeError, ValidationError, IndexError) as exc:
                last_error = exc
                logger.warning(
                    "Invalid verb forms schema on attempt %s/%s",
                    attempt,
                    attempts,
                )
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                logger.warning(
                    "Verb forms request failed on attempt %s/%s: %s",
                    attempt,
                    attempts,
                    exc.__class__.__name__,
                )

            if attempt < attempts:
                await asyncio.sleep(0.5 * attempt)

        raise RuntimeError("OpenAI verb forms request failed.") from last_error

    @staticmethod
    def _normalize_translation_value(raw_value: Union[str, List[str], object]) -> str:
        if isinstance(raw_value, str):
            return raw_value.strip()
        if isinstance(raw_value, list):
            normalized_items = [str(item).strip() for item in raw_value if str(item).strip()]
            return ", ".join(normalized_items)
        return ""
