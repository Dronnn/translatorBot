from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv


class ConfigError(RuntimeError):
    """Raised when required environment configuration is missing or invalid."""


@dataclass(frozen=True)
class Config:
    telegram_bot_token: str
    openai_api_key: str
    openai_model: str = "gpt-5.2"
    translation_cache_db_path: str = "data/translation_cache.sqlite3"
    default_history_limit: int = 10
    history_enabled: bool = True
    log_level: str = "INFO"
    openai_timeout_seconds: float = 30.0
    openai_max_retries: int = 2


def _parse_bool(raw: str | None, default: bool) -> bool:
    if raw is None:
        return default
    normalized = raw.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ConfigError("Invalid boolean value in environment.")


def _require_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise ConfigError(f"Missing required environment variable: {name}")
    return value


def load_config() -> Config:
    """Load and validate environment-backed configuration."""
    load_dotenv()

    telegram_bot_token = _require_env("TELEGRAM_BOT_TOKEN")
    openai_api_key = _require_env("OPENAI_API_KEY")

    openai_model = os.getenv("OPENAI_MODEL", "gpt-5.2").strip() or "gpt-5.2"
    translation_cache_db_path = (
        os.getenv("TRANSLATION_CACHE_DB_PATH", "data/translation_cache.sqlite3").strip()
        or "data/translation_cache.sqlite3"
    )

    try:
        default_history_limit = int(os.getenv("DEFAULT_HISTORY_LIMIT", "10"))
    except ValueError as exc:
        raise ConfigError("DEFAULT_HISTORY_LIMIT must be an integer.") from exc
    if default_history_limit <= 0:
        raise ConfigError("DEFAULT_HISTORY_LIMIT must be greater than 0.")

    try:
        openai_timeout_seconds = float(os.getenv("OPENAI_TIMEOUT_SECONDS", "30"))
    except ValueError as exc:
        raise ConfigError("OPENAI_TIMEOUT_SECONDS must be numeric.") from exc
    if openai_timeout_seconds <= 0:
        raise ConfigError("OPENAI_TIMEOUT_SECONDS must be greater than 0.")

    try:
        openai_max_retries = int(os.getenv("OPENAI_MAX_RETRIES", "2"))
    except ValueError as exc:
        raise ConfigError("OPENAI_MAX_RETRIES must be an integer.") from exc
    if openai_max_retries < 0:
        raise ConfigError("OPENAI_MAX_RETRIES must be >= 0.")

    history_enabled = _parse_bool(os.getenv("HISTORY_ENABLED"), default=True)
    log_level = os.getenv("LOG_LEVEL", "INFO").strip().upper() or "INFO"

    return Config(
        telegram_bot_token=telegram_bot_token,
        openai_api_key=openai_api_key,
        openai_model=openai_model,
        translation_cache_db_path=translation_cache_db_path,
        default_history_limit=default_history_limit,
        history_enabled=history_enabled,
        log_level=log_level,
        openai_timeout_seconds=openai_timeout_seconds,
        openai_max_retries=openai_max_retries,
    )
