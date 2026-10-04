# Root-Me SDK — requirements

## Purpose and scope

Build a lightweight, typed Python SDK for [Root-Me](https://www.root-me.org/),
with a simple client object for an existing account and challenges. Manage the
complete login → read → submit flow. No challenge-solving logic or attacks against
challenge services. Messaging, community features and virtual-environment
management are outside the scope. Follow [AGENTS.md](AGENTS.md).

## Authentication

- Accept login/password directly in the client constructor or a local JSON file
  containing both values. No additional authentication methods, browser flags or
  session persistence calls are necessary for normal use.
  Support explicit reuse of an authenticated session. Do not implement API-key
  authentication. The official data API may be used with the login session.
- Manage cookies, expiry, logout and explicit reconnection. Persist sessions only
  when requested, with private permissions; never persist passwords in sessions.
- Manage JavaScript assistance automatically when needed, including browser
  discovery/setup and credential entry. Keep the isolated browser/session alive
  for subsequent operations. Do not prompt on stdin. Expose a meaningful error
  if native platform verification cannot complete without human intervention.
- Use only a graphical browser for password authentication and JavaScript
  assistance. Require a working display and system browser dependencies; fail
  clearly when unavailable. Do not offer headless, HTTP-only or manual login
  alternatives. Wait for native login completion and verify account-only access
  before returning an authenticated client; a cookie alone is insufficient.
- Allow anonymous website reads where Root-Me permits them. Distinguish missing,
  expired/rejected authentication, denied access and human intervention.
- Never forward credentials to challenge services or unrelated hosts, including
  through redirects and attachment downloads.

## Account and challenges

- Read account profile, score and available progression data; discover and update
  the authenticated account's preferences, including supported file controls.
- List/search challenges and categories using verified filters, pagination and
  language selection. Resolve a challenge by identifier or its actual URL.
- Read statement, metadata, points, difficulty, resource links, attachments and
  available launch/access instructions. Download caller-selected resources.
- Submit a supplied answer once and return accepted, rejected, already solved,
  temporarily blocked or indeterminate, with useful feedback and waiting data.
- Use observed platform flows and actual response shapes. Prefer the official
  data API where covered, authenticated through the session. Do not invent routes.
- Account changes and answer submissions require an explicit client method.
  Generic website mutations are implementation details, not a public interface.

## Reliability and delivery

- Bound timeouts, redirects and read retries. Respect rate limits and Retry-After.
  Never replay a mutation after an ambiguous failure; release owned resources.
- Detect login pages, JavaScript gates and unexpected responses. Do not infer
  submission success from HTTP 200 or unrelated form feedback.
- Never emit passwords, session cookies or submitted answers in logs/errors or
  committed fixtures. Document installation, authentication, reuse and submission.
- Provide pyproject.toml, uv.lock, a locked Nix devShell, local/CI commands and a
  typed public package. Nix is the development environment only.
- Enforce Ruff lint/format, strict mypy, 100% applicable SDK docstrings and 100%
  complete-SDK unit coverage. Automated tests are offline, with synthetic fixtures
  and mocked boundaries; add useful multi-module scenarios.
- Document manual platform observations separately from offline tests. Real-account
  checks are occasional validation, not an integration suite required by CI.
- Build and verify a wheel and source archive. The repository and GitHub releases
  remain private. PyPI publication is deferred and disabled until explicitly
  enabled and configured. Releases follow AGENTS.md.

## Observed behavior — 2026-10-04

The [official API](https://api.www.root-me.org/?lang=en) documents challenge and
account data through a spip_session cookie. Answer submission uses the website's
validation_challenge form and passe control. A fresh supplied-password login
worked in a graphical browser without human input. Both constructor credential
sources were verified without human input, including preferences and challenge
reads. Native login responses can use redirects or AJAX; keep the login page alive
until completion. Browser response bodies are already decompressed. API challenge
links can be relative website paths. A fresh headless login encountered Anubis,
so that authentication route is excluded. Live already-solved feedback uses a
success class inside the challenge validation form.
