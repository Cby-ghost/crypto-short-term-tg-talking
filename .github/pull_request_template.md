## Linked task

Closes #

## Summary

Describe the behavior changed and why.

## Files changed

List the main files and the purpose of each change.

## Validation

- [ ] `python -m compileall -q src tests`
- [ ] `pytest -q`
- [ ] New or changed behavior has deterministic tests
- [ ] Existing tests still pass

## Trading and security review

- [ ] Uses confirmed closed candles where required
- [ ] No look-ahead bias, repainting, or future-data leakage introduced
- [ ] Missing/stale/warm-up data remains conservative
- [ ] No real-order execution or private account API capability added
- [ ] No secrets, tokens, `.env` contents, credentials, or private data committed
- [ ] No direct merge to `main`

## Risk and limitations

State any remaining limitations, assumptions, operational risks, or follow-up work.
