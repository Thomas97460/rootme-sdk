# rootme-sdk

An unofficial, typed Python SDK for [Root-Me](https://www.root-me.org/): automated login, session reuse, profile and challenge exploration, and answer submission.

<p align="center">
  <a href="https://github.com/Thomas97460/rootme-sdk/actions/workflows/ci.yml">
    <img src="https://github.com/Thomas97460/rootme-sdk/actions/workflows/ci.yml/badge.svg" alt="CI">
  </a>
  <a href="https://pypi.org/project/rootme-sdk/">
    <img src="https://img.shields.io/pypi/v/rootme-sdk?style=flat-square&color=00d7d7&label=pypi" alt="pypi">
  </a>
  <a href="https://github.com/Thomas97460/rootme-sdk/releases/latest">
    <img src="https://img.shields.io/github/v/release/Thomas97460/rootme-sdk?style=flat-square&color=00d7d7&label=latest" alt="latest">
  </a>
  <a href="https://github.com/Thomas97460/rootme-sdk/actions/workflows/ci.yml">
    <img src="https://img.shields.io/badge/coverage-100%25-00d7d7?style=flat-square" alt="coverage">
  </a>
  <a href="https://github.com/Thomas97460/rootme-sdk/actions/workflows/ci.yml">
    <img src="https://img.shields.io/badge/types-mypy%20strict-00d7d7?style=flat-square" alt="mypy">
  </a>
  <a href="https://www.python.org/">
    <img src="https://img.shields.io/badge/python-3.13%2B-00d7d7?style=flat-square" alt="python">
  </a>
  <a href="https://github.com/Thomas97460/rootme-sdk/blob/main/LICENSE">
    <img src="https://img.shields.io/badge/license-MIT-00d7d7?style=flat-square" alt="license">
  </a>
</p>

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

### 1. Search challenges and get full details

```python
from rootme_sdk import Category, Difficulty, RootMeClient

with RootMeClient("your-username", "your-password") as client:
    # Search challenges by category, difficulty or title
    for item in client.search_challenges(
        category=Category.WEB_SERVER, difficulty=Difficulty.VERY_EASY
    ):
        print(f"[{item.id}] {item.title} ({item.score} pts)")

    # Get complete challenge details, statement and resources
    challenge = client.get_challenge(5)
    print(f"Title: {challenge.title}")
    print(f"Statement: {challenge.statement}")

    # Read account profile
    profile = client.get_profile()
    print(f"User: {profile.username}, Score: {profile.score}, Rank: {profile.rank}")
```

Alternatively, pass credentials via a JSON file:

```json
{"login": "your-username", "password": "your-password"}
```

```python
with RootMeClient(credentials_file=".secrets/credentials.json") as client:
    profile = client.get_profile()
    print(f"User: {profile.username}, Score: {profile.score}")
```

### 2. Submit a flag

```python
from rootme_sdk import RootMeClient, SubmissionStatus

with RootMeClient("your-username", "your-password") as client:
    result = client.submit_flag(5, "flag{your_flag_here}")

    if result.status == SubmissionStatus.ACCEPTED:
        print("Flag validated!")
    elif result.status == SubmissionStatus.ALREADY_SOLVED:
        print("Challenge already solved.")
    elif result.status == SubmissionStatus.REJECTED:
        print("Incorrect flag.")
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
