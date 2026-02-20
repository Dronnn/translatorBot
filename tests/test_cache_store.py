from bot.cache_store import TranslationCacheStore


def test_cache_returns_entry_for_each_language(tmp_path) -> None:
    db_path = tmp_path / "cache.sqlite3"
    store = TranslationCacheStore(str(db_path))

    store.save_full_translations(
        translations={
            "ru": "дружба",
            "en": "friendship",
            "de": "Freundschaft",
            "hy": "բարեկամություն",
        }
    )

    by_ru = store.find_by_text("дружба")
    by_en = store.find_by_text("friendship")
    by_de = store.find_by_text("Freundschaft")
    by_hy = store.find_by_text("բարեկամություն")

    assert by_ru is not None
    assert by_en is not None
    assert by_de is not None
    assert by_hy is not None

    assert by_ru.matched_language == "ru"
    assert by_en.matched_language == "en"
    assert by_de.matched_language == "de"
    assert by_hy.matched_language == "hy"

    assert by_ru.entry.translations["en"] == "friendship"
    assert by_en.entry.translations["ru"] == "дружба"
    assert by_de.entry.translations["hy"] == "բարեկամություն"
    assert by_hy.entry.translations["de"] == "Freundschaft"

    store.close()


def test_cache_can_store_german_governance(tmp_path) -> None:
    db_path = tmp_path / "cache.sqlite3"
    store = TranslationCacheStore(str(db_path))

    store.save_full_translations(
        translations={
            "ru": "участвовать",
            "en": "participate",
            "de": "teilnehmen",
            "hy": "մասնակցել",
        }
    )
    store.save_german_verb_governance_for_text(
        text="участвовать",
        governance="teilnehmen an + D",
    )

    cached = store.find_by_text("teilnehmen")
    assert cached is not None
    assert cached.entry.german_verb_governance == "teilnehmen an + D"

    store.close()


def test_cache_can_store_german_noun_article_line(tmp_path) -> None:
    db_path = tmp_path / "cache.sqlite3"
    store = TranslationCacheStore(str(db_path))

    store.save_full_translations(
        translations={
            "ru": "картон",
            "en": "cardboard",
            "de": "Pappe",
            "hy": "ստվարաթուղթ",
        },
        german_noun_article_line="die Pappe (f.)",
    )
    cached = store.find_by_text("pappe")
    assert cached is not None
    assert cached.entry.german_noun_article_line == "die Pappe (f.)"

    store.close()


def test_cache_finds_entry_by_past_forms(tmp_path) -> None:
    db_path = tmp_path / "cache.sqlite3"
    store = TranslationCacheStore(str(db_path))

    store.save_full_translations(
        translations={
            "ru": "участвовать",
            "en": "participate",
            "de": "teilnehmen",
            "hy": "մասնակցել",
        },
        verb_past_forms_line=(
            "DE: Perfekt: hat teilgenommen; Prateritum: nahm teil | "
            "EN: Past Simple: participated; Past Participle: participated | "
            "RU: участвовал/участвовала | HY: մասնակցեց"
        ),
        past_lookup_values={
            "ru_past": "участвовал",
            "en_past_simple": "participated",
            "en_past_participle": "participated",
            "de_perfekt": "hat teilgenommen",
            "de_prateritum": "nahm teil",
            "hy_past": "մասնակցեց",
        },
    )

    by_de_perfekt = store.find_by_text("hat teilgenommen")
    by_en_past = store.find_by_text("participated")
    by_ru_past = store.find_by_text("участвовал")
    by_hy_past = store.find_by_text("մասնակցեց")

    assert by_de_perfekt is not None
    assert by_en_past is not None
    assert by_ru_past is not None
    assert by_hy_past is not None

    assert by_de_perfekt.matched_language == "de"
    assert by_en_past.matched_language == "en"
    assert by_ru_past.matched_language == "ru"
    assert by_hy_past.matched_language == "hy"
    assert by_de_perfekt.entry.verb_past_forms_line is not None

    store.close()
