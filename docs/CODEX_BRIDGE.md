# GPT ↔ Codex Bridge

## Purpose

This repository can receive a finalized specification as a GitHub issue and automatically ask Codex to implement it on an isolated branch. Codex runs the test suite and the workflow opens a pull request for human review. It never merges or deploys automatically.

## Normal communication flow

1. Discuss strategy and requirements with GPT.
2. When the specification is final, GPT creates an issue whose title starts with `[codex]`.
3. The owner-triggered GitHub Actions workflow starts Codex.
4. Codex edits source and tests in branch `codex/issue-<number>`.
5. The workflow rejects changes to secrets, runtime data, or `.github/workflows/`.
6. The workflow runs `python -m pytest -q`.
7. If validation passes, it pushes the branch and opens a pull request.
8. GPT and the repository owner review the pull request. Codex does not merge or deploy it.

## One-time repository settings

### Required secret

Create this repository secret under **Settings → Secrets and variables → Actions**:

- `OPENAI_API_KEY`: an OpenAI Platform API key with an appropriate spending limit.

The secret must never be placed in an issue, commit, `.env.example`, workflow log, or chat message.

### Required workflow permissions

Under **Settings → Actions → General → Workflow permissions**:

- Select **Read and write permissions**.
- Enable **Allow GitHub Actions to create and approve pull requests** if GitHub exposes that option.

## Dispatch requirements

The worker runs only when all of these conditions are true:

- The issue is opened or reopened.
- Its title starts with `[codex]`.
- The triggering actor is the repository owner or the explicitly listed ChatGPT GitHub connector bot.

Do not broaden the trusted actor list to `*`.

## Safety boundaries

Automatically dispatched work cannot:

- Edit GitHub workflow files.
- Read or commit secrets.
- Change production configuration or runtime databases.
- Place real orders, transfer funds, change leverage, merge PRs, or deploy.

Tasks involving trading logic still require human review for look-ahead bias, event timing, stale market data, alert deduplication, and risk controls.

## Failure behavior

If Codex produces no changes, touches prohibited files, or fails tests, the workflow stops without opening a pull request. Review the Actions log, clarify the issue specification, then reopen a corrected issue or create a new one.
