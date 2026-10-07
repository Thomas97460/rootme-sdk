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

Copy a snippet, replace the credentials and run it. Login opens a Chromium window
and fills the form automatically.

### 1. Find a challenge by its name and read its statement

```python
from rootme_sdk import RootMeClient

with RootMeClient("your-username", "your-password") as client:
    summary = next(client.search_challenges(query="ELF x86 - 0 protection"))
    challenge = client.get_challenge(summary.id)
    print(challenge.id, challenge.title)  # 41 ELF x86 - 0 protection
    print(challenge.statement)
```

### 2. Download the challenge files

```python
from rootme_sdk import RootMeClient

with RootMeClient("your-username", "your-password") as client:
    print(client.download_files(41))  # (PosixPath('ch1.zip'),)
```

### 3. Submit a flag

```python
from rootme_sdk import RootMeClient

with RootMeClient("your-username", "your-password") as client:
    result = client.submit_flag(41, "your-flag")
    print(result.status, result.message)  # SubmissionStatus.ACCEPTED ...
```

### 4. Browse challenges with filters

```python
from rootme_sdk import Category, Difficulty, RootMeClient

with RootMeClient("your-username", "your-password") as client:
    for item in client.search_challenges(
        category=Category.CRACKING, difficulty=Difficulty.EASY, limit=20
    ):
        print(f"[{item.id}] {item.title} ({item.score} pts)")
```

### 5. Reuse a session

```python
from rootme_sdk import RootMeClient

with RootMeClient(
    credentials_file=".secrets/credentials.json", session_file=".secrets/session.json"
) as client:
    print(client.get_challenge(41).title)
```

`session_file` reuses the saved session while Root-Me still accepts it and logs in
with the credentials only when the file is missing, invalid, expired or rejected.
Rate limits and network failures are raised instead of triggering a new login. The
file is updated after login and on close, and `logout()` deletes it. Prefer this over
logging in on every run.

Credentials can also come from a JSON file `{"login": "...", "password": "..."}`:
`RootMeClient(credentials_file="credentials.json")`.

## Important Notes

- **Graphical Display**: Password login uses an isolated, headed Chromium browser to handle Root-Me's native login flow. A working graphical display is required (`DISPLAY` on Linux).
- **Rate Limits**: Root-Me throttles bursts with HTTP 429, sometimes for several minutes. The client waits at least 2 seconds between requests by default (`min_request_interval=2`); keep this pace across clients and processes sharing one network address. `RateLimitedError.retry_after` gives the server's waiting interval when one is sent, and `submit_flag` returns `SubmissionStatus.BLOCKED` instead of raising. Wait at least that long before calling again; do not wrap SDK calls in automatic retry loops, and never resubmit an answer automatically.
- **Network Family**: Connections use the system's IPv4/IPv6 selection. To pin one family, pass a bound transport, e.g. `RootMeClient(..., transport=httpx.HTTPTransport(local_address="0.0.0.0"))` for IPv4 or `local_address="::"` for IPv6.
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
