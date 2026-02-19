# Telegram Translator Bot (RU/EN/DE/HY)

Telegram bot for translating between Russian (`ru`), English (`en`), German (`de`), and Armenian (`hy`) using OpenAI (`gpt-5.2`).

## Features

- Auto-detect input language and translate into the other 3 supported languages.
- Explicit pair translation in message prefix:
  - `de-ru: Hallo`
  - `de-ru Hallo`
  - `de ru: Hallo`
  - `de→ru: Hallo`
- Language alias normalization (Latin, Cyrillic, Armenian).
- `/lang` inline selection for a default pair.
- `/history` in-memory per-user translation history.
- Input safety rules:
  - ignores empty messages;
  - rejects non-text updates;
  - rejects messages longer than 500 chars.

## Supported Commands

- `/start` — capabilities overview
- `/help` — usage examples
- `/lang` — select default pair
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
