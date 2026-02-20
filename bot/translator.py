from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum

from bot.cache_store import CachedTranslationEntry, TranslationCacheStore
from bot.lang_codes import SUPPORTED_LANGUAGES, is_supported_language
from bot.openai_client import OpenAITranslationClient, OpenAIVerbFormsResult
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
    german_verb_governance: str | None = None
    german_noun_article_line: str | None = None
    verb_past_forms_line: str | None = None


@dataclass(frozen=True)
class VerbEnrichment:
    source_text: str
    target_translations: dict[str, str]
    past_forms_line: str | None
    past_lookup_values: dict[str, str] | None


class TranslationService:
    def __init__(
        self,
        client: OpenAITranslationClient,
        cache_store: TranslationCacheStore,
    ) -> None:
        self._client = client
        self._cache_store = cache_store
        self._logger = logging.getLogger(__name__)

    async def translate(self, request: TranslationRequest) -> TranslationResult:
        if request.mode == ParseMode.EXPLICIT_PAIR:
            return await self._translate_explicit_pair(request)
        if request.mode == ParseMode.FORCED_SOURCE_ALL:
            if not request.src:
                return TranslationResult(
                    status=TranslationStatus.ERROR,
                    error_message="Forced-source mode requires source language.",
                )
            return await self.translate_auto_with_forced_source(
                text=request.text,
                source_language=request.src,
            )
        if request.mode == ParseMode.DEFAULT_PAIR:
            return await self._translate_default_pair(request)
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

        cached_entry = self._cache_store.find_by_language_text(
            language=source_language,
            text=text,
        )
        if cached_entry:
            cached_targets = self._targets_from_entry(
                entry=cached_entry,
                exclude_language=source_language,
            )
            if cached_targets:
                noun_article_line = await self._resolve_german_noun_article(
                    source_language=source_language,
                    source_text=text,
                    translations=cached_targets,
                    cached_noun_article_line=cached_entry.german_noun_article_line,
                    cache_lookup_text=text,
                )
                self._logger.info(
                    "translation_cache_hit mode=auto_forced source=%s",
                    source_language,
                )
                return TranslationResult(
                    status=TranslationStatus.OK,
                    source_language=source_language,
                    translations=cached_targets,
                    german_verb_governance=cached_entry.german_verb_governance,
                    german_noun_article_line=noun_article_line,
                    verb_past_forms_line=cached_entry.verb_past_forms_line,
                )

        targets = [lang for lang in SUPPORTED_LANGUAGES if lang != source_language]
        model_result = await self._client.translate(
            text=text,
            requested_targets=targets,
            forced_source=source_language,
            allowed_languages=list(SUPPORTED_LANGUAGES),
        )
        if not model_result.translations:
            return TranslationResult(
                status=TranslationStatus.ERROR,
                error_message="No translations returned.",
            )

        translations = {
            lang: model_result.translations.get(lang, "").strip()
            for lang in targets
            if model_result.translations.get(lang, "").strip()
        }
        if not translations:
            return TranslationResult(
                status=TranslationStatus.ERROR,
                error_message="No translations returned.",
            )

        enrichment = await self._maybe_enrich_with_verb_forms(
            source_language=source_language,
            source_text=text,
            translations=translations,
        )
        source_text_for_cache = enrichment.source_text
        translations_for_result = enrichment.target_translations

        governance = await self._resolve_german_verb_governance(
            source_language=source_language,
            source_text=source_text_for_cache,
            translations=translations_for_result,
            cached_governance=None,
            cache_lookup_text=text,
        )
        noun_article_line = await self._resolve_german_noun_article(
            source_language=source_language,
            source_text=source_text_for_cache,
            translations=translations_for_result,
            cached_noun_article_line=None,
            cache_lookup_text=text,
        )
        self._save_full_cache_if_possible(
            source_language=source_language,
            source_text=source_text_for_cache,
            translations=translations_for_result,
            german_verb_governance=governance,
            german_noun_article_line=noun_article_line,
            verb_past_forms_line=enrichment.past_forms_line,
            past_lookup_values=enrichment.past_lookup_values,
        )

        return TranslationResult(
            status=TranslationStatus.OK,
            source_language=source_language,
            translations=translations_for_result,
            german_verb_governance=governance,
            german_noun_article_line=noun_article_line,
            verb_past_forms_line=enrichment.past_forms_line,
        )

    async def _translate_explicit_pair(self, request: TranslationRequest) -> TranslationResult:
        if not request.src or not request.dst:
            return TranslationResult(
                status=TranslationStatus.ERROR,
                error_message="Explicit pair requires source and target.",
            )

        cached_entry = self._cache_store.find_by_language_text(
            language=request.src,
            text=request.text,
        )
        if cached_entry:
            cached_translation = cached_entry.translations.get(request.dst, "").strip()
            if cached_translation:
                noun_article_line = await self._resolve_german_noun_article(
                    source_language=request.src,
                    source_text=request.text,
                    translations={request.dst: cached_translation},
                    cached_noun_article_line=cached_entry.german_noun_article_line,
                    cache_lookup_text=request.text,
                )
                self._logger.info(
                    "translation_cache_hit mode=explicit source=%s target=%s",
                    request.src,
                    request.dst,
                )
                return TranslationResult(
                    status=TranslationStatus.OK,
                    source_language=request.src,
                    translations={request.dst: cached_translation},
                    german_verb_governance=cached_entry.german_verb_governance,
                    german_noun_article_line=noun_article_line,
                    verb_past_forms_line=cached_entry.verb_past_forms_line,
                )

        model_result = await self._client.translate(
            text=request.text,
            requested_targets=[request.dst],
            forced_source=request.src,
            allowed_languages=[request.src, request.dst],
        )
        translation = model_result.translations.get(request.dst, "").strip()
        if not translation:
            return TranslationResult(
                status=TranslationStatus.ERROR,
                error_message="No translation returned.",
            )

        governance = await self._resolve_german_verb_governance(
            source_language=request.src,
            source_text=request.text,
            translations={request.dst: translation},
            cached_governance=None,
            cache_lookup_text=request.text,
        )
        noun_article_line = await self._resolve_german_noun_article(
            source_language=request.src,
            source_text=request.text,
            translations={request.dst: translation},
            cached_noun_article_line=None,
            cache_lookup_text=request.text,
        )

        return TranslationResult(
            status=TranslationStatus.OK,
            source_language=request.src,
            translations={request.dst: translation},
            german_verb_governance=governance,
            german_noun_article_line=noun_article_line,
            verb_past_forms_line=None,
        )

    async def _translate_default_pair(self, request: TranslationRequest) -> TranslationResult:
        if not request.src or not request.dst:
            return TranslationResult(
                status=TranslationStatus.ERROR,
                error_message="Default pair requires two languages.",
            )

        pair_languages = [request.src, request.dst]
        if pair_languages[0] == pair_languages[1]:
            return TranslationResult(
                status=TranslationStatus.ERROR,
                error_message="Invalid default pair configuration.",
            )

        src_cached_entry = self._cache_store.find_by_language_text(
            language=request.src,
            text=request.text,
        )
        src_target_translation = ""
        if src_cached_entry:
            src_target_translation = src_cached_entry.translations.get(request.dst, "").strip()

        dst_cached_entry = self._cache_store.find_by_language_text(
            language=request.dst,
            text=request.text,
        )
        dst_target_translation = ""
        if dst_cached_entry:
            dst_target_translation = dst_cached_entry.translations.get(request.src, "").strip()

        # For active pair mode, prefer target-side cache hit to follow user ambiguity rule.
        if dst_cached_entry and dst_target_translation:
            noun_article_line = await self._resolve_german_noun_article(
                source_language=request.dst,
                source_text=request.text,
                translations={request.src: dst_target_translation},
                cached_noun_article_line=dst_cached_entry.german_noun_article_line,
                cache_lookup_text=request.text,
            )
            self._logger.info(
                "translation_cache_hit mode=default source=%s target=%s",
                request.dst,
                request.src,
            )
            return TranslationResult(
                status=TranslationStatus.OK,
                source_language=request.dst,
                translations={request.src: dst_target_translation},
                german_verb_governance=dst_cached_entry.german_verb_governance,
                german_noun_article_line=noun_article_line,
                verb_past_forms_line=dst_cached_entry.verb_past_forms_line,
            )

        if src_cached_entry and src_target_translation:
            noun_article_line = await self._resolve_german_noun_article(
                source_language=request.src,
                source_text=request.text,
                translations={request.dst: src_target_translation},
                cached_noun_article_line=src_cached_entry.german_noun_article_line,
                cache_lookup_text=request.text,
            )
            self._logger.info(
                "translation_cache_hit mode=default source=%s target=%s",
                request.src,
                request.dst,
            )
            return TranslationResult(
                status=TranslationStatus.OK,
                source_language=request.src,
                translations={request.dst: src_target_translation},
                german_verb_governance=src_cached_entry.german_verb_governance,
                german_noun_article_line=noun_article_line,
                verb_past_forms_line=src_cached_entry.verb_past_forms_line,
            )

        model_result = await self._client.translate(
            text=request.text,
            requested_targets=pair_languages,
            forced_source=None,
            allowed_languages=pair_languages,
        )

        detected = self._resolve_default_pair_source_language(
            text=request.text,
            detected=model_result.detected_language,
            pair_source=request.src,
            pair_target=request.dst,
            model_translations=model_result.translations,
        )

        target = pair_languages[1] if detected == pair_languages[0] else pair_languages[0]
        translation = model_result.translations.get(target, "").strip()

        if not translation:
            refill_result = await self._client.translate(
                text=request.text,
                requested_targets=[target],
                forced_source=detected,
                allowed_languages=pair_languages,
            )
            translation = refill_result.translations.get(target, "").strip()

        if not translation:
            return TranslationResult(
                status=TranslationStatus.ERROR,
                error_message="No translation returned for active pair.",
            )

        governance = await self._resolve_german_verb_governance(
            source_language=detected,
            source_text=request.text,
            translations={target: translation},
            cached_governance=None,
            cache_lookup_text=request.text,
        )
        noun_article_line = await self._resolve_german_noun_article(
            source_language=detected,
            source_text=request.text,
            translations={target: translation},
            cached_noun_article_line=None,
            cache_lookup_text=request.text,
        )

        return TranslationResult(
            status=TranslationStatus.OK,
            source_language=detected,
            translations={target: translation},
            german_verb_governance=governance,
            german_noun_article_line=noun_article_line,
            verb_past_forms_line=None,
        )

    async def _translate_auto_all(self, text: str) -> TranslationResult:
        cached_match = self._cache_store.find_by_text(text)
        if cached_match:
            cached_targets = self._targets_from_entry(
                entry=cached_match.entry,
                exclude_language=cached_match.matched_language,
            )
            if cached_targets:
                noun_article_line = await self._resolve_german_noun_article(
                    source_language=cached_match.matched_language,
                    source_text=text,
                    translations=cached_targets,
                    cached_noun_article_line=cached_match.entry.german_noun_article_line,
                    cache_lookup_text=text,
                )
                self._logger.info(
                    "translation_cache_hit mode=auto_all source=%s",
                    cached_match.matched_language,
                )
                return TranslationResult(
                    status=TranslationStatus.OK,
                    source_language=cached_match.matched_language,
                    translations=cached_targets,
                    german_verb_governance=cached_match.entry.german_verb_governance,
                    german_noun_article_line=noun_article_line,
                    verb_past_forms_line=cached_match.entry.verb_past_forms_line,
                )

        model_result = await self._client.translate(
            text=text,
            requested_targets=list(SUPPORTED_LANGUAGES),
            forced_source=None,
            allowed_languages=list(SUPPORTED_LANGUAGES),
        )

        detected = model_result.detected_language
        if detected == "unknown" or not is_supported_language(detected):
            fallback_source = self._guess_fallback_source_language(text)
            if fallback_source:
                fallback_result = await self.translate_auto_with_forced_source(
                    text=text,
                    source_language=fallback_source,
                )
                if fallback_result.status == TranslationStatus.OK:
                    self._logger.info(
                        "translation_fallback_source_applied source=%s",
                        fallback_source,
                    )
                    return fallback_result
            return TranslationResult(status=TranslationStatus.NEEDS_LANGUAGE_CLARIFICATION)

        detected = self._maybe_prefer_german_for_ambiguous_latin_word(
            text=text,
            detected=detected,
            german_translation=model_result.translations.get("de", ""),
        )

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
                allowed_languages=list(SUPPORTED_LANGUAGES),
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

        enrichment = await self._maybe_enrich_with_verb_forms(
            source_language=detected,
            source_text=text,
            translations=translations,
        )
        source_text_for_cache = enrichment.source_text
        translations_for_result = enrichment.target_translations

        governance = await self._resolve_german_verb_governance(
            source_language=detected,
            source_text=source_text_for_cache,
            translations=translations_for_result,
            cached_governance=None,
            cache_lookup_text=text,
        )
        noun_article_line = await self._resolve_german_noun_article(
            source_language=detected,
            source_text=source_text_for_cache,
            translations=translations_for_result,
            cached_noun_article_line=None,
            cache_lookup_text=text,
        )
        self._save_full_cache_if_possible(
            source_language=detected,
            source_text=source_text_for_cache,
            translations=translations_for_result,
            german_verb_governance=governance,
            german_noun_article_line=noun_article_line,
            verb_past_forms_line=enrichment.past_forms_line,
            past_lookup_values=enrichment.past_lookup_values,
        )

        return TranslationResult(
            status=TranslationStatus.OK,
            source_language=detected,
            translations=translations_for_result,
            german_verb_governance=governance,
            german_noun_article_line=noun_article_line,
            verb_past_forms_line=enrichment.past_forms_line,
        )

    def _save_full_cache_if_possible(
        self,
        *,
        source_language: str,
        source_text: str,
        translations: dict[str, str],
        german_verb_governance: str | None,
        german_noun_article_line: str | None,
        verb_past_forms_line: str | None,
        past_lookup_values: dict[str, str] | None,
    ) -> None:
        full_translations: dict[str, str] = {}
        source_value = source_text.strip()
        if not source_value:
            return
        full_translations[source_language] = source_value

        for lang in SUPPORTED_LANGUAGES:
            if lang == source_language:
                continue
            value = translations.get(lang, "").strip()
            if not value:
                return
            full_translations[lang] = value

        self._cache_store.save_full_translations(
            translations=full_translations,
            german_verb_governance=german_verb_governance,
            german_noun_article_line=german_noun_article_line,
            verb_past_forms_line=verb_past_forms_line,
            past_lookup_values=past_lookup_values,
        )
        self._logger.info(
            "translation_cache_saved source=%s",
            source_language,
        )

    @staticmethod
    def _targets_from_entry(
        *,
        entry: CachedTranslationEntry,
        exclude_language: str,
    ) -> dict[str, str]:
        return {
            lang: entry.translations.get(lang, "").strip()
            for lang in SUPPORTED_LANGUAGES
            if lang != exclude_language and entry.translations.get(lang, "").strip()
        }

    async def _maybe_enrich_with_verb_forms(
        self,
        *,
        source_language: str,
        source_text: str,
        translations: dict[str, str],
    ) -> VerbEnrichment:
        source_value = source_text.strip()
        if not self._should_try_verb_forms(source_value):
            return VerbEnrichment(
                source_text=source_value,
                target_translations=translations,
                past_forms_line=None,
                past_lookup_values=None,
            )

        full_translations = self._build_full_translations(
            source_language=source_language,
            source_text=source_value,
            translations=translations,
        )
        if not full_translations:
            return VerbEnrichment(
                source_text=source_value,
                target_translations=translations,
                past_forms_line=None,
                past_lookup_values=None,
            )

        try:
            verb_forms = await self._client.verb_forms(
                source_language=source_language,
                source_text=source_value,
                known_translations=full_translations,
            )
        except Exception:  # noqa: BLE001
            return VerbEnrichment(
                source_text=source_value,
                target_translations=translations,
                past_forms_line=None,
                past_lookup_values=None,
            )

        return self._apply_verb_forms(
            source_language=source_language,
            fallback_source_text=source_value,
            fallback_translations=translations,
            verb_forms=verb_forms,
        )

    @staticmethod
    def _should_try_verb_forms(text: str) -> bool:
        if not text:
            return False
        if len(text) > 60:
            return False
        if any(char in text for char in ",.;:!?()[]{}"):
            return False
        words = text.split()
        if not words or len(words) > 3:
            return False
        return True

    @staticmethod
    def _build_full_translations(
        *,
        source_language: str,
        source_text: str,
        translations: dict[str, str],
    ) -> dict[str, str] | None:
        full_translations: dict[str, str] = {source_language: source_text}
        for lang in SUPPORTED_LANGUAGES:
            if lang == source_language:
                continue
            value = translations.get(lang, "").strip()
            if not value:
                return None
            full_translations[lang] = value
        return full_translations

    def _apply_verb_forms(
        self,
        *,
        source_language: str,
        fallback_source_text: str,
        fallback_translations: dict[str, str],
        verb_forms: OpenAIVerbFormsResult,
    ) -> VerbEnrichment:
        if not verb_forms.is_verb:
            return VerbEnrichment(
                source_text=fallback_source_text,
                target_translations=fallback_translations,
                past_forms_line=None,
                past_lookup_values=None,
            )

        infinitives = {
            lang: str(verb_forms.infinitives.get(lang, "")).strip()
            for lang in SUPPORTED_LANGUAGES
        }
        if any(not infinitives[lang] for lang in SUPPORTED_LANGUAGES):
            return VerbEnrichment(
                source_text=fallback_source_text,
                target_translations=fallback_translations,
                past_forms_line=None,
                past_lookup_values=None,
            )

        source_infinitive = infinitives[source_language]
        target_infinitives = {
            lang: infinitives[lang]
            for lang in SUPPORTED_LANGUAGES
            if lang != source_language
        }

        past_forms_line = self._format_past_forms_line(verb_forms)
        if not past_forms_line:
            return VerbEnrichment(
                source_text=fallback_source_text,
                target_translations=fallback_translations,
                past_forms_line=None,
                past_lookup_values=None,
            )

        past_lookup_values = {
            "ru_past": str(verb_forms.past_lookup.get("ru_past", "")).strip(),
            "en_past_simple": str(verb_forms.past_lookup.get("en_past_simple", "")).strip(),
            "en_past_participle": str(verb_forms.past_lookup.get("en_past_participle", "")).strip(),
            "de_perfekt": str(verb_forms.past_lookup.get("de_perfekt", "")).strip(),
            "de_prateritum": str(verb_forms.past_lookup.get("de_prateritum", "")).strip(),
            "hy_past": str(verb_forms.past_lookup.get("hy_past", "")).strip(),
        }
        if any(not value for value in past_lookup_values.values()):
            return VerbEnrichment(
                source_text=fallback_source_text,
                target_translations=fallback_translations,
                past_forms_line=None,
                past_lookup_values=None,
            )

        return VerbEnrichment(
            source_text=source_infinitive,
            target_translations=target_infinitives,
            past_forms_line=past_forms_line,
            past_lookup_values=past_lookup_values,
        )

    @staticmethod
    def _format_past_forms_line(verb_forms: OpenAIVerbFormsResult) -> str | None:
        de = str(verb_forms.past_display.get("de", "")).strip()
        en = str(verb_forms.past_display.get("en", "")).strip()
        ru = str(verb_forms.past_display.get("ru", "")).strip()
        hy = str(verb_forms.past_display.get("hy", "")).strip()
        if not all((de, en, ru, hy)):
            return None
        return f"DE: {de} | EN: {en} | RU: {ru} | HY: {hy}"

    async def _resolve_german_verb_governance(
        self,
        *,
        source_language: str,
        source_text: str,
        translations: dict[str, str],
        cached_governance: str | None,
        cache_lookup_text: str,
    ) -> str | None:
        if cached_governance:
            return cached_governance

        german_text = self._extract_german_text(
            source_language=source_language,
            source_text=source_text,
            translations=translations,
        )
        if not german_text:
            return None
        if "," in german_text or ";" in german_text:
            return None
        if len(german_text.split()) > 4:
            return None
        # German nouns are capitalized; skip expensive governance lookup for obvious non-verbs.
        if german_text[:1].isupper():
            return None

        try:
            governance = await self._client.german_verb_governance(german_text=german_text)
        except Exception:  # noqa: BLE001
            return None

        if governance:
            self._cache_store.save_german_verb_governance_for_text(
                text=cache_lookup_text,
                governance=governance,
            )
        return governance

    async def _resolve_german_noun_article(
        self,
        *,
        source_language: str,
        source_text: str,
        translations: dict[str, str],
        cached_noun_article_line: str | None,
        cache_lookup_text: str,
    ) -> str | None:
        if cached_noun_article_line:
            return cached_noun_article_line

        german_text = self._extract_german_text(
            source_language=source_language,
            source_text=source_text,
            translations=translations,
        )
        if not german_text:
            return None
        if "," in german_text or ";" in german_text:
            return None
        if len(german_text.split()) > 3:
            return None

        request_text = german_text
        if len(german_text.split()) == 1 and german_text[:1].islower():
            request_text = german_text[:1].upper() + german_text[1:]

        try:
            noun_article_line = await self._client.german_noun_article(german_text=request_text)
        except Exception:  # noqa: BLE001
            return None

        if noun_article_line:
            self._cache_store.save_german_noun_article_for_text(
                text=cache_lookup_text,
                noun_article_line=noun_article_line,
            )
        return noun_article_line

    @staticmethod
    def _extract_german_text(
        *,
        source_language: str,
        source_text: str,
        translations: dict[str, str],
    ) -> str | None:
        if source_language == "de":
            value = source_text.strip()
            return value or None
        value = translations.get("de", "").strip()
        return value or None

    @staticmethod
    def _resolve_default_pair_source_language(
        *,
        text: str,
        detected: str,
        pair_source: str,
        pair_target: str,
        model_translations: dict[str, str],
    ) -> str:
        if detected not in {pair_source, pair_target}:
            return pair_target

        # Ambiguous single-word forms (same spelling in both langs of active pair):
        # follow user preference and treat active target as source.
        if detected == pair_source:
            target_side_value = str(model_translations.get(pair_target, "")).strip()
            if TranslationService._is_ambiguous_single_word_match(text, target_side_value):
                return pair_target
        return detected

    @staticmethod
    def _is_ambiguous_single_word_match(text: str, translated: str) -> bool:
        left = " ".join(text.strip().lower().split())
        right = " ".join(translated.strip().lower().split())
        if not left or not right:
            return False
        if " " in left or " " in right:
            return False
        return left == right

    @staticmethod
    def _guess_fallback_source_language(text: str) -> str | None:
        lower_text = text.lower()
        if any("а" <= char <= "я" or char == "ё" for char in lower_text):
            return "ru"
        if any("ա" <= char <= "ֆ" for char in lower_text):
            return "hy"
        if any(char.isalpha() for char in lower_text):
            # For unresolved Latin-script single words, prefer German.
            return "de"
        return None

    @staticmethod
    def _maybe_prefer_german_for_ambiguous_latin_word(
        *,
        text: str,
        detected: str,
        german_translation: str,
    ) -> str:
        if detected != "en":
            return detected

        raw = text.strip()
        if not raw or " " in raw:
            return detected
        if not raw.isascii() or not raw.isalpha():
            return detected

        de_value = german_translation.strip()
        if not de_value:
            return detected
        if de_value.lower() == raw.lower():
            return "de"
        return detected
