# Architecture

## Overview

The bot is organized into independent layers:

- transport layer (Telegram handlers)
- parsing + validation layer
- translation orchestration layer
- OpenAI API gateway
- supporting infrastructure (config, logging, history, keyboards)

## Modules

- `bot/main.py`
  - App wiring and handler registration.
  - Bot commands registration via `set_my_commands`.
- `bot/config.py`
  - Environment loading and validation.
  - Fails fast for missing required secrets.
- `bot/logging_setup.py`
  - Structured logging and token redaction.
  - Suppresses noisy HTTP request logs.
- `bot/lang_codes.py`
  - Supported language set (`ru`, `en`, `de`, `hy`).
  - Language alias normalization.
  - Pair canonicalization for bidirectional default pairs.
- `bot/parser.py`
  - Input parsing and validation.
  - Modes:
    - `explicit_pair`
    - `default_pair`
    - `auto_all`
- `bot/openai_client.py`
  - OpenAI request/response adapter with retries.
  - Strict response normalization (string/list variants).
- `bot/translator.py`
  - Core translation logic.
  - Handles directional explicit pair, bidirectional active pair, and auto-all.
- `bot/keyboards.py`
  - `/lang` pair keyboard and language-clarification keyboard.
- `bot/history.py`
  - In-memory per-user bounded history store.
- `bot/handlers.py`
  - Telegram commands, callbacks, and message routing.
  - Multilingual UI messages (RU/EN/DE/HY).

## Request Lifecycle

1. A Telegram update arrives.
2. `handlers.on_text_message` parses input via `parse_message_text`.
3. Parser returns one mode:
   - `explicit_pair`: directional translation to one target.
   - `default_pair`: active bidirectional pair from `/lang`.
   - `auto_all`: detect source and translate to remaining 3 languages.
4. Handler calls `translator.translate(...)`.
5. Translator requests OpenAI through `openai_client.translate(...)`.
6. Response is normalized and validated.
7. Handler formats and sends the final reply.
8. Successful request is added to history (if enabled).

## Behavior Notes

- Explicit pair prefix is directional (`de-en ...` != `en-de ...`).
- Active pair from `/lang` is bidirectional (`en-ru` == `ru-en`).
- In active pair mode, messages without prefix are interpreted within the selected two-language scope.

## Error Handling

- Empty text: ignored.
- Non-text updates: fixed multilingual message.
- Text length >500: fixed multilingual rejection.
- Invalid pair: fixed multilingual format hint.
- Unknown language in auto-all: clarification keyboard.
- OpenAI failures: safe generic multilingual error.

## State

- Active pair per user: in-memory dict.
- Pending clarification text per user: in-memory dict.
- History per user: bounded deque.

No database is required in current version.
