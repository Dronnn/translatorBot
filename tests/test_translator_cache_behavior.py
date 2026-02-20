import pytest

from bot.cache_store import TranslationCacheStore
from bot.openai_client import OpenAITranslationResult, OpenAIVerbFormsResult
from bot.parser import ParseMode
from bot.translator import TranslationRequest, TranslationService, TranslationStatus


class FakeOpenAIClient:
    def __init__(self) -> None:
        self.translate_calls = 0
        self.verb_forms_calls = 0
        self.governance_calls = 0
        self.noun_calls = 0

    async def translate(
        self,
        *,
        text: str,
        requested_targets: list[str],
        forced_source: str | None,
        allowed_languages: list[str] | None = None,
    ) -> OpenAITranslationResult:
        self.translate_calls += 1
        return OpenAITranslationResult(
            detected_language="ru",
            translations={
                "en": "friendship",
                "de": "Freundschaft",
                "hy": "բարեկամություն",
            },
        )

    async def verb_forms(
        self,
        *,
        source_language: str,
        source_text: str,
        known_translations: dict[str, str],
    ) -> OpenAIVerbFormsResult:
        self.verb_forms_calls += 1
        return OpenAIVerbFormsResult(
            is_verb=False,
            infinitives={},
            past_lookup={},
            past_display={},
        )

    async def german_verb_governance(self, *, german_text: str) -> str | None:
        self.governance_calls += 1
        return None

    async def german_noun_article(self, *, german_text: str) -> str | None:
        self.noun_calls += 1
        return "die Freundschaft (f.)"


class FakeDefaultPairClient:
    def __init__(self, response: OpenAITranslationResult) -> None:
        self._response = response
        self.translate_calls = 0
        self.noun_calls = 0

    async def translate(
        self,
        *,
        text: str,
        requested_targets: list[str],
        forced_source: str | None,
        allowed_languages: list[str] | None = None,
    ) -> OpenAITranslationResult:
        self.translate_calls += 1
        return self._response

    async def verb_forms(
        self,
        *,
        source_language: str,
        source_text: str,
        known_translations: dict[str, str],
    ) -> OpenAIVerbFormsResult:
        return OpenAIVerbFormsResult(
            is_verb=False,
            infinitives={},
            past_lookup={},
            past_display={},
        )

    async def german_verb_governance(self, *, german_text: str) -> str | None:
        return None

    async def german_noun_article(self, *, german_text: str) -> str | None:
        self.noun_calls += 1
        return None


@pytest.mark.asyncio
async def test_auto_all_second_request_uses_cache_without_model_call(tmp_path) -> None:
    store = TranslationCacheStore(str(tmp_path / "cache.sqlite3"))
    client = FakeOpenAIClient()
    service = TranslationService(client=client, cache_store=store)

    request = TranslationRequest(
        mode=ParseMode.AUTO_ALL,
        text="дружба",
    )

    first_result = await service.translate(request)
    assert first_result.status == TranslationStatus.OK
    assert client.translate_calls == 1
    assert client.verb_forms_calls == 1
    assert client.noun_calls == 1

    second_result = await service.translate(request)
    assert second_result.status == TranslationStatus.OK
    assert second_result.translations == first_result.translations

    # No extra model calls on cache hit.
    assert client.translate_calls == 1
    assert client.verb_forms_calls == 1
    assert client.noun_calls == 1
    assert client.governance_calls == 0

    store.close()


@pytest.mark.asyncio
async def test_default_pair_unknown_detection_uses_active_target_as_source(tmp_path) -> None:
    store = TranslationCacheStore(str(tmp_path / "cache.sqlite3"))
    client = FakeDefaultPairClient(
        OpenAITranslationResult(
            detected_language="unknown",
            translations={
                "en": "organic waste",
                "de": "Biogut",
            },
        )
    )
    service = TranslationService(client=client, cache_store=store)

    result = await service.translate(
        TranslationRequest(
            mode=ParseMode.DEFAULT_PAIR,
            text="biogut",
            src="en",
            dst="de",
        )
    )

    assert result.status == TranslationStatus.OK
    assert result.source_language == "de"
    assert result.translations == {"en": "organic waste"}
    assert client.translate_calls == 1

    store.close()


@pytest.mark.asyncio
async def test_default_pair_ambiguous_detection_prefers_active_target_as_source(tmp_path) -> None:
    store = TranslationCacheStore(str(tmp_path / "cache.sqlite3"))
    client = FakeDefaultPairClient(
        OpenAITranslationResult(
            detected_language="en",
            translations={
                "en": "biogut",
                "de": "biogut",
            },
        )
    )
    service = TranslationService(client=client, cache_store=store)

    result = await service.translate(
        TranslationRequest(
            mode=ParseMode.DEFAULT_PAIR,
            text="biogut",
            src="en",
            dst="de",
        )
    )

    assert result.status == TranslationStatus.OK
    assert result.source_language == "de"
    assert result.translations == {"en": "biogut"}
    assert client.translate_calls == 1

    store.close()


@pytest.mark.asyncio
async def test_default_pair_cache_ambiguous_prefers_active_target_as_source(tmp_path) -> None:
    store = TranslationCacheStore(str(tmp_path / "cache.sqlite3"))
    store.save_full_translations(
        translations={
            "ru": "биогут",
            "en": "biogut",
            "de": "Biogut",
            "hy": "բիոգուտ",
        }
    )
    client = FakeDefaultPairClient(
        OpenAITranslationResult(
            detected_language="en",
            translations={
                "en": "biogut",
                "de": "Biogut",
            },
        )
    )
    service = TranslationService(client=client, cache_store=store)

    result = await service.translate(
        TranslationRequest(
            mode=ParseMode.DEFAULT_PAIR,
            text="biogut",
            src="en",
            dst="de",
        )
    )

    assert result.status == TranslationStatus.OK
    assert result.source_language == "de"
    assert result.translations == {"en": "biogut"}
    assert client.translate_calls == 0

    store.close()
