# AGENTS.md

## Project scope

This repository is an OKX market-monitoring and Telegram notification project. Agents may implement analytics, alerts, tests, documentation, and developer tooling.

## Required workflow

1. Read the linked GitHub issue completely before editing.
2. Inspect the existing architecture and reuse current modules where practical.
3. Make the smallest coherent change that satisfies the acceptance criteria.
4. Add or update tests for behavioral changes.
5. Run `python -m pytest -q` before reporting completion.
6. Summarize changed files, tests, assumptions, and unresolved risks.

## Safety boundaries

- Never add real order placement, withdrawal, transfer, leverage-changing, or account-management behavior unless a future issue explicitly authorizes it and a human approves the resulting PR.
- Never access, print, commit, or request API keys, Telegram tokens, private keys, `.env` contents, credentials, or production configuration.
- Do not modify `.github/workflows/`, repository permissions, branch protection, deployment configuration, or secrets as part of an automatically dispatched task.
- Do not merge pull requests or deploy to production.
- Do not weaken dry-run defaults, alert rate limits, validation, deduplication, or failure handling without explicit acceptance criteria.
- Public market-data integrations must degrade safely when APIs are unavailable or stale.
- Avoid future-data leakage in indicators and backtests. Clearly distinguish event time, confirmation time, and notification time.

## Repository conventions

- Python version: 3.11 or newer.
- Source code: `src/`.
- Tests: `tests/`.
- Test command: `python -m pytest -q`.
- Keep secrets in local environment variables or ignored local configuration only.
- Prefer deterministic unit tests; mock external APIs where appropriate.

## Completion standard

A task is complete only when the requested behavior is implemented, relevant tests pass, prohibited files remain untouched, and the PR description documents limitations and operational risk.