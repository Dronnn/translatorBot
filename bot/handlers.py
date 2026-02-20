from __future__ import annotations

import logging

from telegram import Update
from telegram.ext import ContextTypes

from bot.history import TranslationHistory
from bot.keyboards import build_default_pair_keyboard, build_language_clarification_keyboard
from bot.lang_codes import SUPPORTED_LANGUAGES, canonical_pair, language_label, normalize_pair
from bot.parser import ParseErrorCode, ParseMode, parse_message_text
from bot.translator import TranslationRequest, TranslationResult, TranslationService, TranslationStatus

def _ui4(ru: str, en: str, de: str, hy: str) -> str:
    return (
        f"Русский: {ru}\n"
        f"English: {en}\n"
        f"Deutsch: {de}\n"
        f"Հայերեն: {hy}"
    )


NON_TEXT_MESSAGE = _ui4(
    "Я понимаю только текстовые сообщения.",
    "I only understand text messages.",
    "Ich verstehe nur Textnachrichten.",
    "Ես հասկանում եմ միայն տեքստային հաղորդագրություններ։",
)
TOO_LONG_MESSAGE = _ui4(
    "Текст слишком длинный. Отправьте до 500 символов.",
    "Text is too long. Please send up to 500 characters.",
    "Der Text ist zu lang. Bitte sende bis zu 500 Zeichen.",
    "Տեքստը չափազանց երկար է։ Ուղարկեք մինչև 500 նիշ։",
)
INVALID_PAIR_MESSAGE = _ui4(
    "Не распознал пару языков. Формат: ru-en, de-hy и т.д.",
    "Language pair was not recognized. Format: ru-en, de-hy, etc.",
    "Das Sprachpaar wurde nicht erkannt. Format: ru-en, de-hy usw.",
    "Լեզվական զույգը չհաջողվեց ճանաչել։ Ձևաչափը՝ ru-en, de-hy և այլն։",
)
UNKNOWN_LANGUAGE_MESSAGE = _ui4(
    "Не удалось определить язык. Пожалуйста, уточните язык кнопкой ниже.",
    "Could not detect the language. Please select it using the button below.",
    "Die Sprache konnte nicht erkannt werden. Bitte wähle sie mit der Schaltfläche unten.",
    "Չհաջողվեց որոշել լեզուն։ Խնդրում ենք ընտրել այն ներքևի կոճակով։",
)
TRANSLATION_ERROR_MESSAGE = _ui4(
    "Не удалось выполнить перевод. Попробуйте позже.",
    "Could not complete translation. Please try again later.",
    "Die Übersetzung konnte nicht ausgeführt werden. Bitte später erneut versuchen.",
    "Չհաջողվեց կատարել թարգմանությունը։ Խնդրում ենք փորձել ավելի ուշ։",
)
HISTORY_DISABLED_MESSAGE = _ui4(
    "История переводов отключена.",
    "Translation history is disabled.",
    "Der Übersetzungsverlauf ist deaktiviert.",
    "Թարգմանությունների պատմությունը անջատված է։",
)
HISTORY_EMPTY_MESSAGE = _ui4(
    "История пока пуста.",
    "History is empty.",
    "Der Verlauf ist leer.",
    "Պատմությունը դեռ դատարկ է։",
)


def parse_error_message(code: ParseErrorCode) -> str | None:
    if code == ParseErrorCode.EMPTY:
        return None
    if code == ParseErrorCode.TOO_LONG:
        return TOO_LONG_MESSAGE
    if code == ParseErrorCode.INVALID_PAIR:
        return INVALID_PAIR_MESSAGE
    return None


def format_translation_response(
    result: TranslationResult,
    mode: ParseMode,
) -> str:
    translations = result.translations or {}

    lines: list[str] = []
    if mode == ParseMode.AUTO_ALL and result.source_language:
        lines.append(f"Исходный язык: {language_label(result.source_language)}")

    ordered_langs = [lang for lang in SUPPORTED_LANGUAGES if lang in translations]
    for lang in ordered_langs:
        label = language_label(lang)
        lines.append(f"- {label}: {translations[lang]}")

    if result.verb_past_forms_line:
        lines.append(f"Прошедшие формы: {result.verb_past_forms_line}")

    if result.german_noun_article_line:
        lines.append(f"Артикль/род (de): {result.german_noun_article_line}")

    if result.german_verb_governance:
        lines.append(f"Управление (de): {result.german_verb_governance}")

    return "\n".join(lines).strip()


class BotHandlers:
    def __init__(
        self,
        *,
        translator: TranslationService,
        history: TranslationHistory,
        history_limit: int,
    ) -> None:
        self._translator = translator
        self._history = history
        self._history_limit = history_limit
        self._logger = logging.getLogger(__name__)

        self._default_pairs: dict[int, tuple[str, str]] = {}
        self._pending_clarification: dict[int, str] = {}

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        self._logger.info("command=/start user_id=%s", _user_id(update))
        if update.effective_message is None:
            return

        text = _ui4(
            "Я перевожу между 4 языками: ru, en, de, hy. "
            "Отправьте текст, и я определю язык автоматически и дам перевод на остальные 3 языка. "
            "Также поддерживаю явную пару: de-ru: Hallo "
            "и фиксированный исходный язык: de: Hallo или de Hallo. "
            "Команды: /help, /lang, /history.",
            "I translate between 4 languages: ru, en, de, hy. "
            "Send text and I will detect the language automatically and return translations to the other 3 languages. "
            "Explicit pair is also supported: de-ru: Hallo, "
            "and forced source language: de: Hallo or de Hallo. "
            "Commands: /help, /lang, /history.",
            "Ich übersetze zwischen 4 Sprachen: ru, en, de, hy. "
            "Sende Text, ich erkenne die Sprache automatisch und liefere Übersetzungen in die anderen 3 Sprachen. "
            "Explizites Paar wird auch unterstützt: de-ru: Hallo, "
            "sowie feste Ausgangssprache: de: Hallo oder de Hallo. "
            "Befehle: /help, /lang, /history.",
            "Ես թարգմանում եմ 4 լեզուների միջև՝ ru, en, de, hy։ "
            "Ուղարկեք տեքստ, և ես ավտոմատ կճանաչեմ լեզուն ու կտամ թարգմանություն մնացած 3 լեզուներով։ "
            "Աջակցվում է նաև հստակ զույգ՝ de-ru: Hallo, "
            "և ֆիքսված ելքային լեզու՝ de: Hallo կամ de Hallo։ "
            "Հրամաններ՝ /help, /lang, /history։",
        )
        await update.effective_message.reply_text(text)

    async def help(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        self._logger.info("command=/help user_id=%s", _user_id(update))
        if update.effective_message is None:
            return

        text = _ui4(
            "Форматы ввода: "
            "1) авто-режим: Freundschaft; "
            "2) явная пара: de-ru: Hallo, en-hy: Hello; "
            "3) только исходный язык (перевод на остальные 3): de: Hallo или de Hallo; "
            "4) /lang задает двунаправленную активную пару (например English <-> Deutsch). "
            "Разделители пары: '-', '_', '→', пробел перед ':'. Команды: /start, /help, /lang, /history.",
            "Input formats: "
            "1) auto mode: Freundschaft; "
            "2) explicit pair: de-ru: Hallo, en-hy: Hello; "
            "3) source-only mode (translate to other 3): de: Hallo or de Hallo; "
            "4) /lang sets an active bidirectional pair (for example English <-> Deutsch). "
            "Pair delimiters: '-', '_', '→', or space before ':'. Commands: /start, /help, /lang, /history.",
            "Eingabeformate: "
            "1) Auto-Modus: Freundschaft; "
            "2) explizites Paar: de-ru: Hallo, en-hy: Hello; "
            "3) nur Ausgangssprache (Übersetzung in die anderen 3): de: Hallo oder de Hallo; "
            "4) /lang setzt ein aktives bidirektionales Paar (z. B. English <-> Deutsch). "
            "Trennzeichen: '-', '_', '→' oder Leerzeichen vor ':'. Befehle: /start, /help, /lang, /history.",
            "Մուտքի ձևաչափեր՝ "
            "1) ավտո ռեժիմ՝ Freundschaft; "
            "2) հստակ զույգ՝ de-ru: Hallo, en-hy: Hello; "
            "3) միայն ելքային լեզու (թարգմանություն մնացած 3 լեզուներով)՝ de: Hallo կամ de Hallo; "
            "4) /lang հրամանը սահմանում է ակտիվ երկկողմ զույգ (օրինակ՝ English <-> Deutsch)։ "
            "Զույգի բաժանարարներ՝ '-', '_', '→' կամ բացատ ':'-ից առաջ։ Հրամաններ՝ /start, /help, /lang, /history։",
        )
        await update.effective_message.reply_text(text)

    async def lang(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user_id = _user_id(update)
        self._logger.info("command=/lang user_id=%s", user_id)
        if update.effective_message is None:
            return

        current_pair = self._default_pairs.get(user_id)
        if current_pair:
            src, dst = current_pair
            current_line = _ui4(
                f"Текущая активная пара по умолчанию: {language_label(src)} <-> {language_label(dst)}",
                f"Current active default pair: {language_label(src)} <-> {language_label(dst)}",
                f"Aktives Standardpaar: {language_label(src)} <-> {language_label(dst)}",
                f"Ընթացիկ ակտիվ լռելյայն զույգ՝ {language_label(src)} <-> {language_label(dst)}",
            )
        else:
            current_line = _ui4(
                "Текущий режим по умолчанию: Auto (перевод на 3 языка).",
                "Current default mode: Auto (translate to 3 languages).",
                "Aktueller Standardmodus: Auto (Übersetzung in 3 Sprachen).",
                "Ընթացիկ լռելյայն ռեժիմ՝ Auto (թարգմանություն 3 լեզվով)։",
            )

        await update.effective_message.reply_text(
            f"{current_line}\n\n"
            + _ui4(
                "Выберите новую настройку:",
                "Choose a new setting:",
                "Wähle eine neue Einstellung:",
                "Ընտրեք նոր կարգավորում։",
            ),
            reply_markup=build_default_pair_keyboard(),
        )

    async def history_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user_id = _user_id(update)
        self._logger.info("command=/history user_id=%s", user_id)
        if update.effective_message is None:
            return

        if not self._history.enabled:
            await update.effective_message.reply_text(HISTORY_DISABLED_MESSAGE)
            return

        entries = self._history.latest(user_id=user_id, limit=self._history_limit)
        if not entries:
            await update.effective_message.reply_text(HISTORY_EMPTY_MESSAGE)
            return

        lines = []
        for index, entry in enumerate(entries, start=1):
            timestamp = entry.timestamp.strftime("%Y-%m-%d %H:%M UTC")
            targets = ", ".join(entry.targets)
            lines.append(
                f"{index}. {timestamp} | {entry.source_language} -> {targets} | {entry.input_snippet}"
            )

        await update.effective_message.reply_text("\n".join(lines))

    async def on_text_message(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
    ) -> None:
        message = update.effective_message
        if message is None or not message.text:
            return

        user_id = _user_id(update)
        default_pair = self._default_pairs.get(user_id)

        parsed = parse_message_text(message.text, default_pair=default_pair)
        if parsed.error:
            error_message = parse_error_message(parsed.error)
            self._logger.info(
                "translation_rejected user_id=%s reason=%s text_length=%s",
                user_id,
                parsed.error,
                len(message.text or ""),
            )
            if error_message:
                await message.reply_text(error_message)
            return

        request = TranslationRequest(
            mode=parsed.mode,
            text=parsed.text,
            src=parsed.src,
            dst=parsed.dst,
        )

        self._logger.info(
            "translation_accepted user_id=%s mode=%s text_length=%s",
            user_id,
            parsed.mode,
            len(parsed.text),
        )

        try:
            result = await self._translator.translate(request)
        except Exception:  # noqa: BLE001
            self._logger.exception("translation_failed user_id=%s", user_id)
            await message.reply_text(TRANSLATION_ERROR_MESSAGE)
            return

        if result.status == TranslationStatus.NEEDS_LANGUAGE_CLARIFICATION:
            self._pending_clarification[user_id] = parsed.text
            await message.reply_text(
                UNKNOWN_LANGUAGE_MESSAGE,
                reply_markup=build_language_clarification_keyboard(),
            )
            return

        if result.status != TranslationStatus.OK:
            await message.reply_text(TRANSLATION_ERROR_MESSAGE)
            return

        response = format_translation_response(result, parsed.mode)
        await message.reply_text(response)

        if result.source_language and result.translations:
            self._history.add(
                user_id=user_id,
                input_text=parsed.text,
                source_language=result.source_language,
                requested_targets=list(result.translations.keys()),
            )

    async def on_non_text_message(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
    ) -> None:
        self._logger.info("non_text_message user_id=%s", _user_id(update))
        if update.effective_message is not None:
            await update.effective_message.reply_text(NON_TEXT_MESSAGE)

    async def on_set_pair_callback(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
    ) -> None:
        query = update.callback_query
        if query is None or query.data is None:
            return

        await query.answer()
        user_id = _user_id(update)

        if query.data == "setpair:auto":
            self._default_pairs.pop(user_id, None)
            await query.edit_message_text(
                _ui4(
                    "Режим по умолчанию переключен на Auto.",
                    "Default mode switched to Auto.",
                    "Standardmodus auf Auto umgestellt.",
                    "Լռելյայն ռեժիմը փոխվեց Auto-ի։",
                )
            )
            self._logger.info("default_pair_updated user_id=%s mode=auto", user_id)
            return

        try:
            _, src, dst = query.data.split(":", 2)
        except ValueError:
            await query.edit_message_text(INVALID_PAIR_MESSAGE)
            return
        pair = normalize_pair(f"{src}-{dst}")
        if not pair:
            await query.edit_message_text(INVALID_PAIR_MESSAGE)
            return
        canonical = canonical_pair(pair[0], pair[1])
        if not canonical:
            await query.edit_message_text(INVALID_PAIR_MESSAGE)
            return

        self._default_pairs[user_id] = canonical
        await query.edit_message_text(
            _ui4(
                "Пара по умолчанию сохранена (двунаправленно): "
                f"{language_label(canonical[0])} <-> {language_label(canonical[1])}",
                "Default pair saved (bidirectional): "
                f"{language_label(canonical[0])} <-> {language_label(canonical[1])}",
                "Standardpaar gespeichert (bidirektional): "
                f"{language_label(canonical[0])} <-> {language_label(canonical[1])}",
                "Լռելյայն զույգը պահպանված է (երկկողմ): "
                f"{language_label(canonical[0])} <-> {language_label(canonical[1])}",
            )
        )
        self._logger.info(
            "default_pair_updated user_id=%s pair=%s-%s",
            user_id,
            canonical[0],
            canonical[1],
        )

    async def on_clarify_callback(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
    ) -> None:
        query = update.callback_query
        if query is None or query.data is None:
            return

        await query.answer()
        user_id = _user_id(update)

        _, source_language = query.data.split(":", 1)
        text = self._pending_clarification.pop(user_id, None)
        if not text:
            await query.edit_message_text(
                _ui4(
                    "Нет текста для уточнения. Отправьте сообщение заново.",
                    "No text found for clarification. Please send the message again.",
                    "Kein Text zur Klärung gefunden. Bitte sende die Nachricht erneut.",
                    "Պարզաբանման համար տեքստ չի գտնվել։ Խնդրում ենք նորից ուղարկել հաղորդագրությունը։",
                )
            )
            return

        try:
            result = await self._translator.translate_auto_with_forced_source(
                text=text,
                source_language=source_language,
            )
        except Exception:  # noqa: BLE001
            self._logger.exception("clarification_failed user_id=%s", user_id)
            await query.edit_message_text(TRANSLATION_ERROR_MESSAGE)
            return

        if result.status != TranslationStatus.OK:
            await query.edit_message_text(TRANSLATION_ERROR_MESSAGE)
            return

        formatted = format_translation_response(result, ParseMode.AUTO_ALL)
        await query.edit_message_text(formatted)

        if result.source_language and result.translations:
            self._history.add(
                user_id=user_id,
                input_text=text,
                source_language=result.source_language,
                requested_targets=list(result.translations.keys()),
            )


def _user_id(update: Update) -> int:
    user = update.effective_user
    return user.id if user else 0
