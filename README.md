# rootme-sdk

A small, typed Python client for [Root-Me](https://www.root-me.org/): password
login, reusable sessions, account information/preferences, challenge discovery,
statements, attachments and answer submission. Python 3.13 and 3.14 are tested.

## Install

The repository and GitHub releases are private; PyPI publication is deferred.
Install the checkout, or a wheel downloaded from a GitHub release:

```bash
pip install .
# With optional browser assistance:
pip install '.[browser]'
python -m playwright install chromium
```

For development, use `uv sync --locked --extra browser`. On NixOS, pass an
installed browser path, such as
`executable_path="/run/current-system/sw/bin/google-chrome"`. The Nix devShell
provides Playwright's required Node runtime and shared library.

## Login and read

```python
from rootme_sdk import RootMeClient

with RootMeClient() as client:
    client.login("your-login", password_file=".secrets/rootme-password", browser=True)
    client.session.save(".secrets/session.json")
    challenge = client.read_challenge(5)
    print(challenge.statement)
    for item in client.iter_challenges(lang="en", score=5):
        print(item.title)
```

The password file contains the password, with one terminal newline removed.
Create `.secrets` with permissions 700 and the file with permissions 600.
Alternatively, pass `password="..."` from your own credential loader. Session
files contain cookies and no password. There is no API-key authentication.

`login` uses ordinary HTTP by default. Root-Me's Anubis gate can require JavaScript;
`browser=True` explicitly opens an isolated browser and fills the credentials.
A fresh visible-browser login was verified without human input on 2026-10-04.
The saved session then worked headlessly; a fresh headless login was blocked by
Anubis in this environment. Human verification may still be necessary elsewhere.

`get_challenge(id)` reads official API metadata through the authenticated session;
`read_challenge(id_or_url)` reads the full website statement and resource links.
`list_challenges` returns `Collection(items, next_url)`; `iter_challenges` follows
server pagination lazily. Extra metadata stays available in `.data`.
`list_categories(language="fr")` discovers website category links.

For public website reads needing JavaScript, explicitly call
`client.open_browser(authenticate=False)`. To authenticate manually, explicitly
call `client.open_browser()`. Ordinary methods do not prompt or open a browser.

## Reuse and submit

```python
from pathlib import Path
from rootme_sdk import RootMeClient, Session, SubmissionStatus

with RootMeClient(session=Session.load(".secrets/session.json")) as client:
    client.open_browser(headless=True)
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
Reconnect explicitly using `login` when the current session is rejected.

See [CAPABILITIES.md](CAPABILITIES.md) for observed behavior and limitations.
Tests use synthetic fixtures and no live account. Account preference mutations
have not been manually exercised.

## Development and releases

```bash
nix develop
uv sync --locked --extra browser
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
