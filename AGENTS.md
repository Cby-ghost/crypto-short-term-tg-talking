# AGENTS.md

## Project purpose

This repository is an OKX short-term market-monitoring and Telegram-reporting service. It produces analysis and alerts only.

## Non-negotiable safety boundaries

- Never place, modify, cancel, or close real orders.
- Never add private/account trading API calls.
- Never expose, print, commit, or request secrets, tokens, `.env` contents, private keys, or credentials.
- Never weaken dry-run, alert-only, validation, or data-quality safeguards without explicit approval in the linked issue.
- Never merge directly into `main`.
- Do not change GitHub Actions workflows unless the linked issue explicitly authorizes that exact workflow change.

## Required workflow

1. Read the linked GitHub issue completely before editing.
2. Inspect the existing implementation, configuration, documentation, and tests.
3. Make the smallest coherent change that satisfies the issue.
4. Preserve backward compatibility unless the issue explicitly authorizes a breaking change.
5. Add or update tests for every behavioral change.
6. Run:
   - `python -m compileall -q src tests`
   - `pytest -q`
7. Report what changed, tests run, limitations, and any remaining risks.

## Trading-logic requirements

- Use confirmed closed candles only unless the issue explicitly defines another rule.
- Avoid look-ahead bias, future leakage, backfilled signal timestamps, and repainting.
- Keep spot and perpetual CVD separate unless normalization and aggregation are explicitly defined.
- Treat missing, stale, partial, or warm-up data conservatively.
- Preserve deduplication, cooldown, signal-quality gates, and audit logging.
- Any change to scoring, entry, stop-loss, take-profit, fees, slippage, or risk/reward must be stated explicitly in the issue and covered by tests.

## Scope control

- Do not refactor unrelated modules.
- Do not update dependencies unless required by the task.
- Do not edit `config.yaml` production values merely to make tests pass.
- Prefer deterministic tests that do not depend on live OKX or Telegram services.

## Pull request expectations

The PR description must include:

- Linked issue number.
- Summary of behavior changes.
- Files changed.
- Tests and their results.
- Security and trading-risk impact.
- Known limitations or follow-up work.
