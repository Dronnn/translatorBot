# Security Policy

## Supported Scope

This repository contains a Telegram bot that uses external API credentials.
Security issues are handled for active code in `main`.

## Reporting a Vulnerability

Report security concerns privately to the repository owner.
Do not open a public issue containing exploit details or secrets.

## Secret Handling

- Store secrets only in environment variables or local `.env`.
- `.env` must never be committed.
- `.env.example` must contain placeholders only.

## Logging Rules

- Do not log API keys, bot tokens, or full environment dumps.
- Keep logs minimal and focused on operational events.

## Incident Response Basics

If a secret is exposed:

1. Revoke/rotate the secret immediately.
2. Remove secret from runtime files and logs where possible.
3. Update deployments with rotated secrets.
4. Audit recent commits and automation outputs.
