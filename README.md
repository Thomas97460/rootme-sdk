# rootme-sdk

A small, typed Python client for [Root-Me](https://www.root-me.org/): automatic
password login, reusable sessions, account information/preferences, challenge discovery,
statements, attachments and answer submission. Python 3.13 and 3.14 are tested.

## Install

The repository and GitHub releases are private; PyPI publication is deferred.
Install the checkout, or a wheel downloaded from a GitHub release:

```bash
pip install .
```

Browser support is included. When JavaScript is required, the SDK uses an installed
Chrome/Chromium or downloads its managed Chromium automatically on first use.
For development, use `uv sync --locked`; the Nix devShell provides the required
Node runtime and shared library.

## Login and read

```python
from rootme_sdk import RootMeClient

with RootMeClient("your-login", "your-password") as client:
    challenge = client.read_challenge(5)
    print(challenge.statement)
    for item in client.iter_challenges(lang="en", score=5):
        print(item.title)
```

Alternatively, create `.secrets/credentials.json`:

```json
{"login": "your-login", "password": "your-password"}
```

```python
with RootMeClient(credentials_file=".secrets/credentials.json") as client:
    challenge = client.read_challenge(5)
```

Create `.secrets` with permissions 700 and the file with permissions 600. No
browser selection, cookie handling or session file is required. The constructor
authenticates before returning. The client uses Root-Me's native JavaScript login
in an isolated browser automatically. It fills the
credentials and keeps the browser alive for subsequent operations. Passwords are
not retained by the client or saved in sessions. There is no API-key authentication.

Password login always opens a graphical Chrome/Chromium window and fills the
credentials automatically. No manual login is required. A working desktop display
and Chromium's system dependencies are required; Linux needs `DISPLAY`. The SDK
raises `BrowserUnavailableError` before browser startup when that display is missing.
It waits for native login completion and verifies an account-only page before
returning. Platform verification failures, network failures and rate limits remain
explicit errors. There is no headless or HTTP-only login fallback.

`get_challenge(id)` reads official API metadata through the authenticated session;
`read_challenge(id_or_url)` reads the full website statement and resource links.
`list_challenges` returns `Collection(items, next_url)`; `iter_challenges` follows
server pagination lazily. Extra metadata stays available in `.data`.
`list_categories(language="fr")` discovers website category links.

`RootMeClient()` allows anonymous reads, with automatic JavaScript assistance when
needed. To connect an existing client, use `client.login("login", "password")` or
`client.login(credentials_file=".secrets/credentials.json")`.

## Reuse and submit

```python
from pathlib import Path
from rootme_sdk import RootMeClient, SubmissionStatus

with RootMeClient(credentials_file=".secrets/credentials.json") as client:
    challenge = client.read_challenge(5)
    answer = Path(".secrets/answer.txt").read_text().removesuffix("\n")
    result = client.submit_answer(5, answer)
    if result.status == SubmissionStatus.INDETERMINATE:
        print("Inspect platform state before deliberately submitting again.")
```

Results distinguish accepted, rejected, already solved, blocked and indeterminate.
The client refreshes form tokens and submits once. Unknown responses and ambiguous
failures remain indeterminate. Submission feedback is scoped to the challenge
validation form and redacts the supplied answer.

Select an attachment from `challenge.resources`, then use
`client.download(attachment, "attachment.zip")`. Downloads to other hosts receive
no account cookies. Closing the client releases its HTTP pool and browser.

Advanced callers can explicitly save `client.session` and load it with
`RootMeClient(session=Session.load(path))`. Session files contain cookies, never
passwords. Reuse does not renew an expired login: reconnect with credentials.
Website JavaScript assistance uses the same graphical browser when required.

## Account

`get_user(your_account_id)` returns account profile, score, position and additional
API fields, including available validation entries in `.data`. These entries may
be paginated by the platform. `preferences()` exposes the observed editable form;
`update_preferences({"bio": "..."})` explicitly changes selected fields.
`Upload` supports observed avatar/CV controls. Hidden form tokens cannot be
changed by callers. `logout()` requests server logout and clears local state.

## Errors and verification

Catch `RootMeError` or an exported specific error. Authentication errors carry
`reason`: missing, expired or rejected. Rejected credentials can indicate remote
expiry or invalid credentials. `HumanInterventionRequiredError` carries a
verification URL; `RateLimitedError.retry_after` carries the waiting interval.
`BrowserUnavailableError` reports an unavailable graphical browser environment.
Reconnect explicitly using `login` when the current session is rejected. Failed
login attempts are never silently replayed through another mechanism.

See [CAPABILITIES.md](CAPABILITIES.md) for observed behavior and limitations.
Tests use synthetic fixtures and no live account. Account preference mutations
have not been manually exercised.

## Development and releases

```bash
nix develop
uv sync --locked
git config core.hooksPath .githooks
task ci
```

CI enforces Ruff lint/format, strict mypy, 100% SDK docstrings and unit coverage,
offline scenarios, and clean offline wheel/source installation checks.
`authentication/` owns sessions and browser assistance; `parsers/` owns API JSON
and website HTML. The public client coordinates them through the HTTP transport.

An approved `vX.Y.Z` tag publishes the wheel and source archive to a private GitHub
release. PyPI remains disabled unless explicitly enabled after publisher setup.
See [CONTRIBUTING.md](CONTRIBUTING.md), [AGENTS.md](AGENTS.md) and
[REQUIREMENTS.md](REQUIREMENTS.md).

Since 0.3.0, graphical browser login is the only password authentication path.
The constructor still accepts credentials directly or from JSON. Remove calls to
`open_browser` and the former `login` options `browser`, `headless`,
`executable_path` and `password_file`; use the constructor or `login` with either
credential source instead. Explicit session reuse and the `[browser]` installation
extra remain supported, with browser support included by default.
