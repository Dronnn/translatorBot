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


class OpenAITranslationSchema(BaseModel):
    detected_language: Literal["ru", "en", "de", "hy", "unknown"]
    translations: Dict[str, Union[str, List[str]]]


@dataclass(frozen=True)
class OpenAITranslationResult:
    detected_language: str
    translations: dict[str, str]


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

    @staticmethod
    def _normalize_translation_value(raw_value: Union[str, List[str], object]) -> str:
        if isinstance(raw_value, str):
            return raw_value.strip()
        if isinstance(raw_value, list):
            normalized_items = [str(item).strip() for item in raw_value if str(item).strip()]
            return ", ".join(normalized_items)
        return ""
