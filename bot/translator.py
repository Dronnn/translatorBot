from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from bot.lang_codes import SUPPORTED_LANGUAGES, is_supported_language
from bot.openai_client import OpenAITranslationClient
from bot.parser import ParseMode


class TranslationStatus(str, Enum):
    OK = "ok"
    NEEDS_LANGUAGE_CLARIFICATION = "needs_language_clarification"
    ERROR = "error"


@dataclass(frozen=True)
class TranslationRequest:
    mode: ParseMode
    text: str
    src: str | None = None
    dst: str | None = None


@dataclass(frozen=True)
class TranslationResult:
    status: TranslationStatus
    source_language: str | None = None
    translations: dict[str, str] | None = None
    error_message: str | None = None


class TranslationService:
    def __init__(self, client: OpenAITranslationClient) -> None:
        self._client = client

    async def translate(self, request: TranslationRequest) -> TranslationResult:
        if request.mode == ParseMode.EXPLICIT_PAIR:
            return await self._translate_explicit_pair(request)
        return await self._translate_auto_all(request.text)

    async def translate_auto_with_forced_source(
        self,
        *,
        text: str,
        source_language: str,
    ) -> TranslationResult:
        if not is_supported_language(source_language):
            return TranslationResult(
                status=TranslationStatus.ERROR,
                error_message="Unsupported source language.",
            )

        targets = [lang for lang in SUPPORTED_LANGUAGES if lang != source_language]
        model_result = await self._client.translate(
            text=text,
            requested_targets=targets,
            forced_source=source_language,
        )
        if not model_result.translations:
            return TranslationResult(
                status=TranslationStatus.ERROR,
                error_message="No translations returned.",
            )

        return TranslationResult(
            status=TranslationStatus.OK,
            source_language=source_language,
            translations=model_result.translations,
        )

    async def _translate_explicit_pair(self, request: TranslationRequest) -> TranslationResult:
        if not request.src or not request.dst:
            return TranslationResult(
                status=TranslationStatus.ERROR,
                error_message="Explicit pair requires source and target.",
            )

        model_result = await self._client.translate(
            text=request.text,
            requested_targets=[request.dst],
            forced_source=request.src,
        )
        translation = model_result.translations.get(request.dst, "").strip()
        if not translation:
            return TranslationResult(
                status=TranslationStatus.ERROR,
                error_message="No translation returned.",
            )

        return TranslationResult(
            status=TranslationStatus.OK,
            source_language=request.src,
            translations={request.dst: translation},
        )

    async def _translate_auto_all(self, text: str) -> TranslationResult:
        model_result = await self._client.translate(
            text=text,
            requested_targets=list(SUPPORTED_LANGUAGES),
            forced_source=None,
        )

        detected = model_result.detected_language
        if detected == "unknown" or not is_supported_language(detected):
            return TranslationResult(status=TranslationStatus.NEEDS_LANGUAGE_CLARIFICATION)

        targets = [lang for lang in SUPPORTED_LANGUAGES if lang != detected]
        translations = {
            lang: model_result.translations.get(lang, "").strip()
            for lang in targets
            if model_result.translations.get(lang, "").strip()
        }

        missing_targets = [lang for lang in targets if lang not in translations]
        if missing_targets:
            refill_result = await self._client.translate(
                text=text,
                requested_targets=missing_targets,
                forced_source=detected,
            )
            for lang in missing_targets:
                value = refill_result.translations.get(lang, "").strip()
                if value:
                    translations[lang] = value

        if not translations:
            return TranslationResult(
                status=TranslationStatus.ERROR,
                error_message="No translations returned.",
            )

        return TranslationResult(
            status=TranslationStatus.OK,
            source_language=detected,
            translations=translations,
        )
