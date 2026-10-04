# Root-Me SDK — requirements

## Purpose

Build a lightweight Python SDK that lets another program interact with
[Root-Me](https://www.root-me.org/) using an existing user account: manage
authentication end to end, discover and read challenges, and submit an answer.
Provide a simple Python client object with methods, typed results and documented
errors. No challenge-solving logic or execution of attacks against challenge
services. Follow [AGENTS.md](AGENTS.md); choose and justify the architecture,
dependencies, supported Python versions and exact public signatures during
implementation.

## Authentication and access

- Investigate the actual login and submission flows before implementing them.
  Support username/password where possible, an existing session, and an API key
  where accepted. Do not assume these grant identical capabilities.
- Manage cookies, authentication state, expiry, reconnection and logout. Allow
  explicit session reuse between program runs without persisting passwords;
  session persistence must be opt-in and treat its contents as secrets.
- When a browser or human step is needed, expose an actionable state to the
  caller and allow the operation to resume afterwards. A normal SDK call must
  never unexpectedly prompt on stdin or open a browser. Fully unattended use
  should work whenever the platform permits it.
- Allow genuinely anonymous reads without credentials. Require authentication
  only for operations that need it, and distinguish missing authentication,
  expired credentials, insufficient permissions and human intervention.
- Hide platform-specific authentication details behind the client. Never send
  account credentials or session cookies to challenge services or unrelated
  hosts, including through redirects or resource downloads.

## Functional scope

- List/search challenges and categories, with the available filters, pagination
  and language selection. Retrieve a challenge by a stable reference such as its
  identifier or URL.
- Read its statement, metadata, points, difficulty, links, supporting resources
  and available files; allow callers to download those files. Expose available
  launch/access instructions and connection information. Support platform-side
  challenge activation when needed to obtain access, without solving it.
- Submit a caller-provided answer and return the platform's actual outcome:
  accepted, rejected, already solved, temporarily blocked, or indeterminate when
  confirmation is unavailable. Preserve useful feedback and waiting information.
- Expose all verified capabilities available to the account, including reads
  and writes beyond challenges: profiles/preferences, scores, rankings,
  progression, community interactions and virtual-environment management wherever
  supported by the platform. Prioritize the complete authenticate → read → submit
  flow, then cover the remaining capabilities.
- Inventory verified operations in a concise capability table: method, purpose,
  access requirement and limitations. Prefer the official API where it covers
  the need; use verified web flows for missing capabilities. Do not invent
  endpoints or equate public data with anonymous API access.
- Every mutation requires an explicit SDK method call; reading or reconnecting
  must not silently trigger unrelated changes. Document capabilities that cannot
  be automated and the reason, including any required human interaction.

## Reliability and developer experience

- Keep common use cases short; document installation, anonymous reads,
  authenticated reads, session reuse, human handoff and submission with examples.
  Return useful structured data rather than requiring callers to parse HTML or
  make raw requests themselves.
- Provide bounded timeouts and retries, respect rate limits and `Retry-After`,
  and release network/browser resources predictably. Never automatically replay
  a submission or other mutation after an ambiguous failure.
- Detect unexpected responses, login pages and platform/protection changes;
  report a meaningful error rather than fabricated data or success. Secrets and
  submitted answers must not appear in logs, errors or committed fixtures.

## Delivery and acceptance

- Deliver the installable SDK, a concise README, typed public API, tests and
  local/CI quality commands. Use `pyproject.toml`, `uv` and a locked Nix devShell;
  Nix is only the development environment, not the SDK distribution format.
- Enforce Ruff lint/format, strict mypy, docstring coverage and **100% unit-test
  coverage** as specified in `AGENTS.md`.
- Tests run without external network access, an account or secrets. Use sanitized
  response fixtures and mocked transport; add broader offline scenarios for
  login/session expiry, human handoff, resource retrieval and submission outcomes.
  A timeout after sending an answer must not cause a duplicate submission.
- Document which platform behavior was observed and which remains unverified.
  Offline tests do not prove a live account flow works. No real-account
  integration suite is required; any later manual validation is separate.
- Release the same versioned wheel and source distribution through GitHub
  Releases and PyPI, following the tag approval and verification rules in
  `AGENTS.md`. Target `pip install rootme-sdk`; confirm package-name availability
  and publishing access before the first release.

## Discovery notes — 2026-10-04

The [official API documentation](https://api.www.root-me.org/?lang=en) lists
`/login`, `/challenges`, `/auteurs`, `/classement` and `/environnements_virtuels`,
including detail routes. It describes access using an API key or `spip_session`
cookie, even for public data. Submission is not documented on that page; verify
its actual flow rather than assuming the API supports it.

An automated read of the [main site](https://www.root-me.org/) received an Anubis
access-denied page. This observation does not establish the login flow or whether
every caller needs human intervention; account for this possibility explicitly.
