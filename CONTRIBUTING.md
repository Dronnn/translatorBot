# Contributing

## Workflow

1. Create a feature branch from `main`.
2. Keep changes scoped and atomic.
3. Update tests when behavior changes.
4. Open PR with clear problem/solution summary.

## Commit Style

Use concise imperative commit messages, for example:

- `Add parser support for explicit pair without colon`
- `Harden logging to avoid token leakage`

## Code Quality

- Keep business logic in service/modules, not in Telegram handlers only.
- Avoid logging sensitive data.
- Keep user-facing error messages deterministic.

## Testing

Run tests on runtime host (old Mac):

```bash
source .venv/bin/activate
pytest
```

## Security Rules

- Never commit `.env` or real tokens.
- Never include secrets in logs, screenshots, or issue text.
- Use `.env.example` placeholders only.
