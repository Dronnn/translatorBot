# Commands And Input Rules

## Bot Commands

### `/start`

Shows capabilities summary and supported languages.

### `/help`

Shows input formats and examples.

### `/lang`

Opens inline keyboard for active **bidirectional** pair selection.

- Example pair selection: `English <-> Deutsch`
- This means plain text is accepted in either language and translated to the other one.

### `/history`

Shows latest N translation entries for user session if enabled.

## Input Modes

### 1) Auto-all mode

If no prefix is provided and no active pair is set:
- bot detects source language (`ru/en/de/hy`)
- translates to the other 3 languages

Example:

```text
Freundschaft
```

### 2) Explicit directional pair mode

If pair prefix is provided in message start, translation is directional and to one target.

Supported styles:

- `de-ru: Hallo`
- `de-ru Hallo`
- `de ru: Hallo`
- `de→ru: Hallo`

### 3) Active bidirectional pair mode

If active pair is set with `/lang` and message has no pair prefix:
- bot constrains detection to pair languages only
- bot translates into the opposite language of the pair

Example active pair: `English <-> Deutsch`

- Input: `Vater` -> output in English
- Input: `father` -> output in German

## Validation Rules

- Empty text: ignored.
- Non-text updates (sticker/photo/voice/video):
  - bot replies with multilingual fixed text-only warning.
- Text >500 chars:
  - bot replies with multilingual fixed length warning.
- Invalid pair prefix:
  - bot replies with multilingual format hint.

## Interface Language

Bot interface messages (commands, help, errors, status messages) are shown in all 4 languages:

- Русский
- English
- Deutsch
- Հայերեն
