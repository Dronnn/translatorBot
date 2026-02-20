# Telegram Translator Bot (RU/EN/DE/HY)

Telegram bot for translating between Russian (`ru`), English (`en`), German (`de`), and Armenian (`hy`) using OpenAI (`gpt-5.2`).

## Features

- Auto-detect input language and translate into the other 3 supported languages.
- Persistent SQLite cache for 4-language translation sets (`ru/en/de/hy`), so repeated words are served from DB.
- Verb-aware output:
  - if input is a verb (including past forms), translations are normalized to infinitive forms;
  - extra line with key past forms for `ru/en/de/hy`;
  - German governance line for verbs (for example `teilnehmen an + D`).
- German noun output:
  - separate line with article and gender (for example `die Pappe (f.)`).
- Explicit pair translation in message prefix:
  - `de-ru: Hallo`
  - `de-ru Hallo`
  - `de ru: Hallo`
  - `de→ru: Hallo`
- Forced-source mode (translate to the other 3 languages without auto-detection):
  - `de: Hallo`
  - `de Hallo`
- Language alias normalization (Latin, Cyrillic, Armenian).
- `/lang` inline selection for an active **bidirectional** pair.
  - `en-ru` is treated the same as `ru-en`.
  - When an active pair is set, messages without prefix are accepted in either of those two languages and translated to the other one.
- `/history` in-memory per-user translation history.
- Bot interface messages are shown in all 4 languages (RU/EN/DE/HY) for commands, help, and validation errors.
- Input safety rules:
  - ignores empty messages;
  - rejects non-text updates;
  - rejects messages longer than 500 chars.

## Supported Commands

- `/start` — capabilities overview
- `/help` — usage examples
- `/lang` — select active bidirectional pair
- `/history` — recent translations

## Runtime Policy

- Development machine: code + docs only.
- Runtime/install/tests: old Mac only.
- Secrets: only env vars or local `.env`.

## Configuration

Copy `.env.example` to `.env` on runtime host and set real values.

| Variable | Required | Default | Description |
|---|---|---|---|
| `TELEGRAM_BOT_TOKEN` | yes | - | BotFather token |
| `OPENAI_API_KEY` | yes | - | OpenAI API key |
| `OPENAI_MODEL` | no | `gpt-5.2` | Model for translation |
| `TRANSLATION_CACHE_DB_PATH` | no | `data/translation_cache.sqlite3` | Local SQLite path for translation cache |
| `DEFAULT_HISTORY_LIMIT` | no | `10` | `/history` depth |
| `HISTORY_ENABLED` | no | `true` | Enable history |
| `LOG_LEVEL` | no | `INFO` | Log level |
| `OPENAI_TIMEOUT_SECONDS` | no | `30` | API timeout |
| `OPENAI_MAX_RETRIES` | no | `2` | OpenAI retry count |

## Setup (Old Mac)

```bash
git clone <your_repo_url>
cd translatorBot
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
cp .env.example .env
# edit .env with real values
```

## Run (Old Mac)

```bash
source .venv/bin/activate
python -m bot.main
```

## Test (Old Mac)

```bash
source .venv/bin/activate
pytest
```

## Pair Behavior

- Explicit prefix stays directional:
  - `de-en Vater` means translate German -> English.
- Forced source keeps language fixed and returns the other 3 languages:
  - `de: Vater` and `de Vater` skip language detection.
- `/lang` active pair is bidirectional:
  - if active pair is `English <-> Deutsch`, then plain `Vater` translates to English and plain `father` translates to German.

## Deployment Update (Old Mac)

```bash
cd ~/apps/translatorBot
source .venv/bin/activate
git pull
pip install -r requirements.txt
# restart your bot process manager / service
```

## Security

- `.env` and logs are git-ignored.
- Logger redacts common secret patterns.
- HTTP request logs that could expose bot tokens are suppressed.
- Never commit real secrets.

## Project Structure

```text
.
├── .github/
├── bot/
├── tests/
├── .env.example
├── .gitignore
├── CONTRIBUTING.md
├── SECURITY.md
├── requirements.txt
└── README.md
```
