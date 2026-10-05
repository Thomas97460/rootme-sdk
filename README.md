# rootme-sdk

An unofficial, typed Python SDK for [Root-Me](https://www.root-me.org/): automated login, session reuse, profile and challenge exploration, and answer submission.

> [!NOTE]
> This library is alpha software and is not affiliated with Root-Me. Respect Root-Me's terms of service and rate limits.

## Installation

Requires Python >= 3.13.

### With pip

```bash
# Install
pip install rootme-sdk

# Upgrade
pip install -U rootme-sdk
```

### With uv

```bash
# In a project
uv add rootme-sdk
uv lock --upgrade-package rootme-sdk

# In a virtual environment
uv pip install rootme-sdk
uv pip install -U rootme-sdk
```

Playwright is included. On first use, it automatically uses your local Chrome/Chromium or downloads a managed Chromium browser.

## Quickstart

### 1. Login and read challenges

```python
from rootme_sdk import RootMeClient

# Connect with credentials directly
with RootMeClient("your-username", "your-password") as client:
    # Read a challenge statement
    challenge = client.read_challenge(5)
    print(f"Title: {challenge.title}")
    print(f"Statement: {challenge.statement}")

    # Browse challenges
    for item in client.iter_challenges(lang="en", score=5):
        print(f"[{item.id}] {item.title} ({item.score} pts)")
```

Alternatively, pass credentials via a JSON file:

```json
{"login": "your-username", "password": "your-password"}
```

```python
with RootMeClient(credentials_file=".secrets/credentials.json") as client:
    user = client.get_user(12345)
    print(f"User: {user.nom}, Score: {user.score}")
```

### 2. Submit an answer

```python
from rootme_sdk import RootMeClient, SubmissionStatus

with RootMeClient("your-username", "your-password") as client:
    result = client.submit_answer(5, "flag{your_flag_here}")

    if result.status == SubmissionStatus.ACCEPTED:
        print("Flag validated!")
    elif result.status == SubmissionStatus.ALREADY_SOLVED:
        print("Challenge already solved.")
    elif result.status == SubmissionStatus.REJECTED:
        print("Incorrect flag.")
    elif result.status == SubmissionStatus.INDETERMINATE:
        print(f"Ambiguous response: {result.message}")
```

### 3. Session reuse

Save the session to avoid re-authenticating on every run:

```python
from rootme_sdk import RootMeClient, Session

with RootMeClient("your-username", "your-password") as client:
    client.session.save(".secrets/session.json")

# Later: reload the saved session
with RootMeClient(session=Session.load(".secrets/session.json")) as client:
    challenge = client.read_challenge(5)
```

## Important Notes

- **Graphical Display**: Password login uses an isolated, headed Chromium browser to handle Root-Me's native login flow. A working graphical display is required (`DISPLAY` on Linux).
- **Security**: Never commit your passwords or `.secrets/` directory. Saved sessions contain cookies and should be restricted to your user account.
- **Documentation**:
  - [API Reference](API.md) — Exhaustive methods and types documentation.
  - [Capabilities & Limits](CAPABILITIES.md) — Observed platform behaviors and known limitations.
  - [Contributing](CONTRIBUTING.md) — Development workflow, quality gates, and testing guidelines.
  - [Security Policy](SECURITY.md) — Vulnerability reporting and security practices.

## Development

```bash
nix develop         # or install uv + task manually
uv sync --locked
git config core.hooksPath .githooks
task ci
```
