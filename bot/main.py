from __future__ import annotations

import atexit
import logging

from telegram import BotCommand
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    MessageHandler,
    filters,
)

from bot.cache_store import TranslationCacheStore
from bot.config import ConfigError, load_config
from bot.handlers import BotHandlers
from bot.history import TranslationHistory
from bot.logging_setup import setup_logging
from bot.openai_client import OpenAITranslationClient
from bot.translator import TranslationService

logger = logging.getLogger(__name__)


async def _post_init(application: Application) -> None:
    commands = [
        BotCommand("start", "Описание возможностей"),
        BotCommand("help", "Формат ввода и примеры"),
        BotCommand("lang", "Пара языков по умолчанию"),
        BotCommand("history", "Последние переводы"),
    ]
    await application.bot.set_my_commands(commands)


def create_application() -> Application:
    config = load_config()
    setup_logging(level=config.log_level)
    cache_store = TranslationCacheStore(config.translation_cache_db_path)
    atexit.register(cache_store.close)

    openai_client = OpenAITranslationClient(
        api_key=config.openai_api_key,
        model=config.openai_model,
        timeout_seconds=config.openai_timeout_seconds,
        max_retries=config.openai_max_retries,
    )
    translator = TranslationService(openai_client, cache_store)
    history = TranslationHistory(
        enabled=config.history_enabled,
        limit=config.default_history_limit,
    )
    handlers = BotHandlers(
        translator=translator,
        history=history,
        history_limit=config.default_history_limit,
    )

    app = Application.builder().token(config.telegram_bot_token).post_init(_post_init).build()

    app.add_handler(CommandHandler("start", handlers.start))
    app.add_handler(CommandHandler("help", handlers.help))
    app.add_handler(CommandHandler("lang", handlers.lang))
    app.add_handler(CommandHandler("history", handlers.history_command))

    app.add_handler(CallbackQueryHandler(handlers.on_set_pair_callback, pattern=r"^setpair:"))
    app.add_handler(CallbackQueryHandler(handlers.on_clarify_callback, pattern=r"^clarify:"))

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handlers.on_text_message))
    app.add_handler(
        MessageHandler(
            ~filters.TEXT & ~filters.COMMAND,
            handlers.on_non_text_message,
        )
    )

    return app


def main() -> None:
    try:
        app = create_application()
    except ConfigError as exc:
        raise SystemExit(str(exc)) from exc

    logger.info("Starting polling loop.")
    app.run_polling(allowed_updates=None)


if __name__ == "__main__":
    main()
