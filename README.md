# rootme-sdk

A small, typed Python client for [Root-Me](https://www.root-me.org/): official API
reads, reusable authentication, optional browser assistance, challenge statements,
answer submission and the forms/actions actually offered to your account.
It contains no challenge-solving logic. Python 3.13 and 3.14 are tested.

## Install

From a published release:

```bash
pip install rootme-sdk
# Only when browser assistance is needed:
pip install 'rootme-sdk[browser]'
python -m playwright install chromium
```

Before the first release, install the checkout with `uv sync`. On NixOS, pass an
installed browser path to `open_browser`/`login`, for example
`executable_path="/run/current-system/sw/bin/google-chrome"`. The devShell provides
the Node runtime and shared library needed by Playwright's Python driver.

## API key: reads without a browser

The [official API](https://api.www.root-me.org/?lang=en) accepts an `api_key` cookie
or a `spip_session` cookie. Public data still requires API authentication.

```python
from pathlib import Path
from rootme_sdk import RootMeClient

key = Path(".secrets/rootme-api-key").read_text().strip()
with RootMeClient(api_key=key) as client:
    metadata = client.get_challenge(5)
    for challenge in client.iter_challenges(lang="en", score=5):
        print(challenge.title)
    ranking = client.ranking().items
```

`get_challenge(id)` returns API metadata and any statement provided by the API;
the live API may omit the statement. `read_challenge(id_or_url)` reads the actual
web page. Lists return `Collection(items, next_url)`; `iter_*` follows the
server's pagination lazily. Additional API fields stay available in `.data`.
API keys are never inferred to grant website-writing permissions.

## Password file or manual browser login

```python
from pathlib import Path
from rootme_sdk import RootMeClient

Path(".secrets").mkdir(mode=0o700, exist_ok=True)
with RootMeClient() as client:
    client.login("your-login", password_file=".secrets/rootme-password", browser=True)
    client.session.save(".secrets/session.json")
```

The secret file contains the password; one terminal newline is removed. Restrict
it to your user (`chmod 600 .secrets/rootme-password`). Passwords are used for the
login and never saved in `Session`. To log in manually instead, explicitly call
`client.open_browser()` and use its isolated window. Neither ordinary API calls
nor HTTP-only `login(...)` prompt on stdin or open a browser.

Browser assistance is explicit because the site's Anubis JavaScript verification
may block plain HTTP even with a previously captured cookie. The client retains
the browser for website requests while API requests stay on HTTP. You can request
`headless=True` with supplied credentials; human verification may still be needed.
For public pages requiring JS but no account, use
`client.open_browser(authenticate=False)`.

Manual verification on 2026-10-04 confirmed a fresh username/password login with
`headless=False`, without human input, followed by authenticated preferences and
challenge reads. The saved session then worked with `headless=True`. A fresh
headless login was blocked by Anubis in this environment; unattended use can still
need a visible browser window. Login waits for the authenticated account menu,
not merely the presence of a session cookie.

## Reuse a session, read and submit

```python
from pathlib import Path
from rootme_sdk import RootMeClient, Session, SubmissionStatus

with RootMeClient(session=Session.load(".secrets/session.json")) as client:
    client.open_browser(headless=True)  # Explicitly reuse a browser when JS is needed.
    challenge = client.read_challenge(5)
    print(challenge.statement)
    # Select the attachment you want from challenge.resources before downloading.
    # client.download(attachment, "attachment.zip")
    answer = Path("answer.txt").read_text().removesuffix("\n")
    result = client.submit_answer(5, answer)
    if result.status == SubmissionStatus.INDETERMINATE:
        print("Inspect platform state before deliberately submitting again.")
```

`get_page(url)` exposes readable text, links and `WebForm` objects for other
account functions. `submit_form(form, changes, files=...)` refreshes the form's
tokens before submitting; hidden controls cannot be overridden. `Upload` represents
a file control. `preferences()` and `update_preferences(...)` cover the observed
profile form. `perform_action(url)` explicitly invokes a discovered action link,
including actions implemented by the website as GET requests.

All writes require an explicit caller operation and are never automatically
replayed. Public external downloads receive no account cookies; same-host
attachments may use the web session. Closing a client releases its HTTP pool and
optional browser. `logout()` requests server logout when possible and always
clears local credentials.

## Errors and verification

Catch `RootMeError` or a specific exported error. `AuthenticationRequiredError`
has a `reason` of `missing`, `expired` or `rejected`; rejected credentials can
mean remote expiry or invalid/revoked credentials. `HumanInterventionRequiredError`
provides a verification URL. `RateLimitedError.retry_after` carries the server's
waiting interval. Timeouts and safe-read retry budgets are configurable.

API reads through an authenticated session, automatic password login, browser
challenge reading and preferences discovery were manually observed on 2026-10-04. Tests use synthetic
fixtures with no live account. Real submissions, profile changes and other
mutations have not been manually exercised. See [CAPABILITIES.md](CAPABILITIES.md)
for the exact surface and remaining platform-specific limits.

## Development and releases

```bash
nix develop
uv sync --locked --extra browser
git config core.hooksPath .githooks
task ci
```

CI enforces Ruff formatting/lint, strict mypy, 100% SDK docstring coverage and
100% unit coverage, plus offline scenarios and clean wheel/source installations.
No Root-Me account, browser download or platform network access is needed for tests.

`authentication/` owns session persistence and optional browser authentication;
`parsers/` owns API JSON and website HTML interpretation. The public client
coordinates those modules through the HTTP transport. Shared result models and
errors remain at the package root, and consumers import through `rootme_sdk`.

A human-approved `vX.Y.Z` tag publishes identical artifacts to GitHub and PyPI.
Configure the PyPI Trusted Publisher first; see
[CONTRIBUTING.md](CONTRIBUTING.md). [AGENTS.md](AGENTS.md) defines repository rules;
[REQUIREMENTS.md](REQUIREMENTS.md) describes the intended scope.
