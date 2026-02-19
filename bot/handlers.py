from __future__ import annotations

import logging

from telegram import Update
from telegram.ext import ContextTypes

from bot.history import TranslationHistory
from bot.keyboards import build_default_pair_keyboard, build_language_clarification_keyboard
from bot.lang_codes import SUPPORTED_LANGUAGES, language_label, normalize_pair
from bot.parser import ParseErrorCode, ParseMode, parse_message_text
from bot.translator import TranslationRequest, TranslationResult, TranslationService, TranslationStatus

NON_TEXT_MESSAGE = "Я понимаю только текстовые сообщения."
TOO_LONG_MESSAGE = "Текст слишком длинный. Отправьте до 500 символов."
INVALID_PAIR_MESSAGE = "Не распознал пару языков. Формат: ru-en, de-hy и т.д."
UNKNOWN_LANGUAGE_MESSAGE = "Не удалось определить язык. Пожалуйста, уточните язык кнопкой ниже."
TRANSLATION_ERROR_MESSAGE = "Не удалось выполнить перевод. Попробуйте позже."
HISTORY_DISABLED_MESSAGE = "История переводов отключена."
HISTORY_EMPTY_MESSAGE = "История пока пуста."


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

        text = (
            "Я перевожу между 4 языками: ru, en, de, hy.\n"
            "Отправьте текст, и я определю язык автоматически и дам перевод на остальные 3 языка.\n\n"
            "Я также поддерживаю явную пару: de-ru: Hallo\n"
            "Команды: /help, /lang, /history"
        )
        await update.effective_message.reply_text(text)

    async def help(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        self._logger.info("command=/help user_id=%s", _user_id(update))
        if update.effective_message is None:
            return

        text = (
            "Форматы ввода:\n"
            "1) Авто-режим (на 3 оставшихся языка):\n"
            "   Freundschaft\n\n"
            "2) Явная пара в начале сообщения:\n"
            "   de-ru: Hallo\n"
            "   en-hy: Hello\n\n"
            "Допустимы разделители пары: '-', '_', '→', пробел перед ':'\n"
            "Команды: /start, /help, /lang, /history"
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
            current_line = f"Текущая пара по умолчанию: {language_label(src)} -> {language_label(dst)}"
        else:
            current_line = "Текущий режим по умолчанию: Auto (перевод на 3 языка)"

        await update.effective_message.reply_text(
            f"{current_line}\n\nВыберите новую настройку:",
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
            await query.edit_message_text("Режим по умолчанию переключен на Auto.")
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

        self._default_pairs[user_id] = pair
        await query.edit_message_text(
            f"Пара по умолчанию сохранена: {language_label(pair[0])} -> {language_label(pair[1])}"
        )
        self._logger.info("default_pair_updated user_id=%s pair=%s-%s", user_id, src, dst)

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
            await query.edit_message_text("Нет текста для уточнения. Отправьте сообщение заново.")
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
