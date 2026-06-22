# Security Policy

This project is a read-only/order-intent Bybit Spot bot. It must not place,
cancel, amend, transfer, withdraw, set leverage, or otherwise execute on Bybit.

## Reporting Security Issues

Open a private security advisory in GitHub when available, or contact the
repository owner directly. Do not open public issues containing secrets,
account identifiers, `.env` values, API keys, or exploitable details.

## Scope

Report issues involving:

- hardcoded secrets or accidental secret exposure;
- behavior that can execute on Bybit instead of writing local intents only;
- unsafe handling of read-only account keys or `BYBIT_ALLOW_READ_WRITE_KEY`;
- state-changing API endpoints without explicit security review;
- SQL injection, unsafe path handling, or sensitive data in logs;
- GitHub Actions or Codex automation that can leak secrets or bypass review.

Out of scope:

- live trading performance claims;
- market losses from manually executed intents;
- public-network availability of Bybit or Alternative.me.
