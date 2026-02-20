from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from bot.lang_codes import SUPPORTED_LANGUAGES

_PAST_LOOKUP_TO_COLUMN: dict[str, str] = {
    "ru_past": "ru_past_norm",
    "en_past_simple": "en_past_simple_norm",
    "en_past_participle": "en_past_participle_norm",
    "de_perfekt": "de_perfekt_norm",
    "de_prateritum": "de_prateritum_norm",
    "hy_past": "hy_past_norm",
}

_LANGUAGE_SEARCH_COLUMNS: dict[str, tuple[str, ...]] = {
    "ru": ("ru_norm", "ru_past_norm"),
    "en": ("en_norm", "en_past_simple_norm", "en_past_participle_norm"),
    "de": ("de_norm", "de_perfekt_norm", "de_prateritum_norm"),
    "hy": ("hy_norm", "hy_past_norm"),
}

_ALL_SEARCH_COLUMNS: tuple[str, ...] = (
    "ru_norm",
    "en_norm",
    "de_norm",
    "hy_norm",
    "ru_past_norm",
    "en_past_simple_norm",
    "en_past_participle_norm",
    "de_perfekt_norm",
    "de_prateritum_norm",
    "hy_past_norm",
)


def _normalize_text(text: str) -> str:
    return " ".join(text.strip().lower().split())


@dataclass(frozen=True)
class CachedTranslationEntry:
    translations: dict[str, str]
    german_verb_governance: str | None = None
    german_noun_article_line: str | None = None
    verb_past_forms_line: str | None = None


@dataclass(frozen=True)
class CachedTranslationMatch:
    matched_language: str
    entry: CachedTranslationEntry


class TranslationCacheStore:
    def __init__(self, db_path: str) -> None:
        db_file = Path(db_path)
        if db_file.parent and str(db_file.parent) != ".":
            db_file.parent.mkdir(parents=True, exist_ok=True)

        self._conn = sqlite3.connect(db_file)
        self._conn.row_factory = sqlite3.Row
        self._init_schema()

    def close(self) -> None:
        self._conn.close()

    def find_by_text(self, text: str) -> CachedTranslationMatch | None:
        normalized = _normalize_text(text)
        if not normalized:
            return None

        where_clause = " OR ".join(f"{column} = ?" for column in _ALL_SEARCH_COLUMNS)
        params = tuple(normalized for _ in _ALL_SEARCH_COLUMNS)
        row = self._conn.execute(
            f"""
            SELECT
                ru, en, de, hy,
                de_verb_governance,
                de_noun_article_line,
                verb_past_forms_line,
                ru_norm, en_norm, de_norm, hy_norm,
                ru_past_norm, en_past_simple_norm, en_past_participle_norm,
                de_perfekt_norm, de_prateritum_norm, hy_past_norm
            FROM translation_cache
            WHERE {where_clause}
            ORDER BY updated_at DESC, id DESC
            LIMIT 1
            """,
            params,
        ).fetchone()
        if row is None:
            return None

        translations = {lang: str(row[lang]).strip() for lang in SUPPORTED_LANGUAGES}
        matched_language = self._detect_matched_language(row=row, normalized_input=normalized)
        if matched_language is None:
            return None

        governance = str(row["de_verb_governance"] or "").strip() or None
        noun_article_line = str(row["de_noun_article_line"] or "").strip() or None
        verb_past_forms_line = str(row["verb_past_forms_line"] or "").strip() or None
        return CachedTranslationMatch(
            matched_language=matched_language,
            entry=CachedTranslationEntry(
                translations=translations,
                german_verb_governance=governance,
                german_noun_article_line=noun_article_line,
                verb_past_forms_line=verb_past_forms_line,
            ),
        )

    def find_by_language_text(
        self,
        *,
        language: str,
        text: str,
    ) -> CachedTranslationEntry | None:
        if language not in SUPPORTED_LANGUAGES:
            return None

        normalized = _normalize_text(text)
        if not normalized:
            return None

        search_columns = _LANGUAGE_SEARCH_COLUMNS[language]
        where_clause = " OR ".join(f"{column} = ?" for column in search_columns)
        row = self._conn.execute(
            f"""
            SELECT
                ru, en, de, hy,
                de_verb_governance,
                de_noun_article_line,
                verb_past_forms_line
            FROM translation_cache
            WHERE {where_clause}
            ORDER BY updated_at DESC, id DESC
            LIMIT 1
            """,
            tuple(normalized for _ in search_columns),
        ).fetchone()
        if row is None:
            return None

        governance = str(row["de_verb_governance"] or "").strip() or None
        noun_article_line = str(row["de_noun_article_line"] or "").strip() or None
        verb_past_forms_line = str(row["verb_past_forms_line"] or "").strip() or None
        return CachedTranslationEntry(
            translations={lang: str(row[lang]).strip() for lang in SUPPORTED_LANGUAGES},
            german_verb_governance=governance,
            german_noun_article_line=noun_article_line,
            verb_past_forms_line=verb_past_forms_line,
        )

    def save_full_translations(
        self,
        *,
        translations: Mapping[str, str],
        german_verb_governance: str | None = None,
        german_noun_article_line: str | None = None,
        verb_past_forms_line: str | None = None,
        past_lookup_values: Mapping[str, str] | None = None,
    ) -> None:
        cleaned = {lang: str(translations.get(lang, "")).strip() for lang in SUPPORTED_LANGUAGES}
        if any(not cleaned[lang] for lang in SUPPORTED_LANGUAGES):
            return

        normalized = {f"{lang}_norm": _normalize_text(cleaned[lang]) for lang in SUPPORTED_LANGUAGES}
        if any(not normalized[f"{lang}_norm"] for lang in SUPPORTED_LANGUAGES):
            return

        governance = (german_verb_governance or "").strip() or None
        noun_article_line = (german_noun_article_line or "").strip() or None
        verb_past = (verb_past_forms_line or "").strip() or None
        past_lookup = self._normalize_past_lookup_values(past_lookup_values or {})

        self._conn.execute(
            """
            INSERT INTO translation_cache (
                ru, en, de, hy,
                ru_norm, en_norm, de_norm, hy_norm,
                de_verb_governance,
                de_noun_article_line,
                verb_past_forms_line,
                ru_past_norm,
                en_past_simple_norm,
                en_past_participle_norm,
                de_perfekt_norm,
                de_prateritum_norm,
                hy_past_norm
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(ru_norm, en_norm, de_norm, hy_norm)
            DO UPDATE SET
                ru = excluded.ru,
                en = excluded.en,
                de = excluded.de,
                hy = excluded.hy,
                de_verb_governance = CASE
                    WHEN excluded.de_verb_governance IS NOT NULL
                        THEN excluded.de_verb_governance
                    ELSE translation_cache.de_verb_governance
                END,
                de_noun_article_line = CASE
                    WHEN excluded.de_noun_article_line IS NOT NULL
                        THEN excluded.de_noun_article_line
                    ELSE translation_cache.de_noun_article_line
                END,
                verb_past_forms_line = CASE
                    WHEN excluded.verb_past_forms_line IS NOT NULL
                        THEN excluded.verb_past_forms_line
                    ELSE translation_cache.verb_past_forms_line
                END,
                ru_past_norm = CASE
                    WHEN excluded.ru_past_norm IS NOT NULL
                        THEN excluded.ru_past_norm
                    ELSE translation_cache.ru_past_norm
                END,
                en_past_simple_norm = CASE
                    WHEN excluded.en_past_simple_norm IS NOT NULL
                        THEN excluded.en_past_simple_norm
                    ELSE translation_cache.en_past_simple_norm
                END,
                en_past_participle_norm = CASE
                    WHEN excluded.en_past_participle_norm IS NOT NULL
                        THEN excluded.en_past_participle_norm
                    ELSE translation_cache.en_past_participle_norm
                END,
                de_perfekt_norm = CASE
                    WHEN excluded.de_perfekt_norm IS NOT NULL
                        THEN excluded.de_perfekt_norm
                    ELSE translation_cache.de_perfekt_norm
                END,
                de_prateritum_norm = CASE
                    WHEN excluded.de_prateritum_norm IS NOT NULL
                        THEN excluded.de_prateritum_norm
                    ELSE translation_cache.de_prateritum_norm
                END,
                hy_past_norm = CASE
                    WHEN excluded.hy_past_norm IS NOT NULL
                        THEN excluded.hy_past_norm
                    ELSE translation_cache.hy_past_norm
                END,
                updated_at = CURRENT_TIMESTAMP
            """,
            (
                cleaned["ru"],
                cleaned["en"],
                cleaned["de"],
                cleaned["hy"],
                normalized["ru_norm"],
                normalized["en_norm"],
                normalized["de_norm"],
                normalized["hy_norm"],
                governance,
                noun_article_line,
                verb_past,
                past_lookup["ru_past_norm"],
                past_lookup["en_past_simple_norm"],
                past_lookup["en_past_participle_norm"],
                past_lookup["de_perfekt_norm"],
                past_lookup["de_prateritum_norm"],
                past_lookup["hy_past_norm"],
            ),
        )
        self._conn.commit()

    def save_german_verb_governance_for_text(self, *, text: str, governance: str) -> None:
        normalized = _normalize_text(text)
        governance_value = governance.strip()
        if not normalized or not governance_value:
            return

        where_clause = " OR ".join(f"{column} = ?" for column in _ALL_SEARCH_COLUMNS)
        params = tuple(normalized for _ in _ALL_SEARCH_COLUMNS)
        self._conn.execute(
            f"""
            UPDATE translation_cache
            SET de_verb_governance = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = (
                SELECT id
                FROM translation_cache
                WHERE {where_clause}
                ORDER BY updated_at DESC, id DESC
                LIMIT 1
            )
            """,
            (governance_value, *params),
        )
        self._conn.commit()

    def save_german_noun_article_for_text(self, *, text: str, noun_article_line: str) -> None:
        normalized = _normalize_text(text)
        noun_article_value = noun_article_line.strip()
        if not normalized or not noun_article_value:
            return

        where_clause = " OR ".join(f"{column} = ?" for column in _ALL_SEARCH_COLUMNS)
        params = tuple(normalized for _ in _ALL_SEARCH_COLUMNS)
        self._conn.execute(
            f"""
            UPDATE translation_cache
            SET de_noun_article_line = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = (
                SELECT id
                FROM translation_cache
                WHERE {where_clause}
                ORDER BY updated_at DESC, id DESC
                LIMIT 1
            )
            """,
            (noun_article_value, *params),
        )
        self._conn.commit()

    def _init_schema(self) -> None:
        self._conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS translation_cache (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ru TEXT NOT NULL,
                en TEXT NOT NULL,
                de TEXT NOT NULL,
                hy TEXT NOT NULL,
                ru_norm TEXT NOT NULL,
                en_norm TEXT NOT NULL,
                de_norm TEXT NOT NULL,
                hy_norm TEXT NOT NULL,
                de_verb_governance TEXT,
                de_noun_article_line TEXT,
                verb_past_forms_line TEXT,
                ru_past_norm TEXT,
                en_past_simple_norm TEXT,
                en_past_participle_norm TEXT,
                de_perfekt_norm TEXT,
                de_prateritum_norm TEXT,
                hy_past_norm TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(ru_norm, en_norm, de_norm, hy_norm)
            );

            CREATE INDEX IF NOT EXISTS idx_translation_cache_ru_norm
                ON translation_cache(ru_norm);
            CREATE INDEX IF NOT EXISTS idx_translation_cache_en_norm
                ON translation_cache(en_norm);
            CREATE INDEX IF NOT EXISTS idx_translation_cache_de_norm
                ON translation_cache(de_norm);
            CREATE INDEX IF NOT EXISTS idx_translation_cache_hy_norm
                ON translation_cache(hy_norm);
            CREATE INDEX IF NOT EXISTS idx_translation_cache_ru_past_norm
                ON translation_cache(ru_past_norm);
            CREATE INDEX IF NOT EXISTS idx_translation_cache_en_past_simple_norm
                ON translation_cache(en_past_simple_norm);
            CREATE INDEX IF NOT EXISTS idx_translation_cache_en_past_participle_norm
                ON translation_cache(en_past_participle_norm);
            CREATE INDEX IF NOT EXISTS idx_translation_cache_de_perfekt_norm
                ON translation_cache(de_perfekt_norm);
            CREATE INDEX IF NOT EXISTS idx_translation_cache_de_prateritum_norm
                ON translation_cache(de_prateritum_norm);
            CREATE INDEX IF NOT EXISTS idx_translation_cache_hy_past_norm
                ON translation_cache(hy_past_norm);
            """
        )
        self._add_missing_columns()
        self._conn.commit()

    @staticmethod
    def _detect_matched_language(
        *,
        row: sqlite3.Row,
        normalized_input: str,
    ) -> str | None:
        if normalized_input in {str(row["ru_norm"] or ""), str(row["ru_past_norm"] or "")}:
            return "ru"
        if normalized_input in {str(row["hy_norm"] or ""), str(row["hy_past_norm"] or "")}:
            return "hy"
        # Prefer German over English for ambiguous Latin-script forms that can belong to both.
        if normalized_input in {
            str(row["de_norm"] or ""),
            str(row["de_perfekt_norm"] or ""),
            str(row["de_prateritum_norm"] or ""),
        }:
            return "de"
        if normalized_input in {
            str(row["en_norm"] or ""),
            str(row["en_past_simple_norm"] or ""),
            str(row["en_past_participle_norm"] or ""),
        }:
            return "en"
        return None

    @staticmethod
    def _normalize_past_lookup_values(values: Mapping[str, str]) -> dict[str, str | None]:
        normalized_values: dict[str, str | None] = {}
        for lookup_key, column_name in _PAST_LOOKUP_TO_COLUMN.items():
            value = str(values.get(lookup_key, "")).strip()
            normalized = _normalize_text(value) if value else ""
            normalized_values[column_name] = normalized or None
        return normalized_values

    def _add_missing_columns(self) -> None:
        existing_columns = {
            row["name"]
            for row in self._conn.execute("PRAGMA table_info(translation_cache)").fetchall()
        }
        required_columns: dict[str, str] = {
            "de_noun_article_line": "TEXT",
            "verb_past_forms_line": "TEXT",
            "ru_past_norm": "TEXT",
            "en_past_simple_norm": "TEXT",
            "en_past_participle_norm": "TEXT",
            "de_perfekt_norm": "TEXT",
            "de_prateritum_norm": "TEXT",
            "hy_past_norm": "TEXT",
        }
        for column_name, column_type in required_columns.items():
            if column_name not in existing_columns:
                self._conn.execute(
                    f"ALTER TABLE translation_cache ADD COLUMN {column_name} {column_type}"
                )
