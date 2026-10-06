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

Every example runs inside a connected client. Login opens a graphical Chromium window
and fills the form automatically; you only supply credentials.

```python
from rootme_sdk import RootMeClient

with RootMeClient("your-username", "your-password") as client:
    ...
```

Or `RootMeClient(credentials_file=".secrets/credentials.json")` with
`{"login": "your-username", "password": "your-password"}`.

### 1. Find a challenge by its name

```python
summary = next(client.search_challenges(query="ELF x86 - 0 protection"))
print(summary.id, summary.title)  # 41 ELF x86 - 0 protection
```

### 2. Read its statement

```python
challenge = client.get_challenge(summary.id)
print(challenge.statement)
```

### 3. Download the challenge files

A challenge page exposes two different kinds of links:

- `challenge.files`: the challenge's own material behind the statement's
  *Download the challenge* button (binary, archive, capture, image…).
- `challenge.resources`: documentation and references Root-Me associates with
  the challenge (PDFs, articles, videos).

```python
paths = client.download_files(challenge, "challenges/41")
print(paths)  # (PosixPath('challenges/41/ch1.zip'),)

for resource in challenge.resources:
    print(resource.label, resource.url)  # read or download them only if useful
```

To fetch a single file or resource, use `client.download(resource, "elf.pdf")`.

### 4. Submit a flag

```python
from rootme_sdk import SubmissionStatus

result = client.submit_flag(41, "your-flag")
if result.status == SubmissionStatus.ACCEPTED:
    print("Flag validated!")
else:
    print(result.status, result.message)
```

### 5. Browse challenges with filters

```python
from rootme_sdk import Category, Difficulty

for item in client.search_challenges(
    category=Category.CRACKING, difficulty=Difficulty.EASY, limit=20
):
    print(f"[{item.id}] {item.title} ({item.score} pts)")
```

`score=` targets an exact point value; `query=` and the filters can be combined.

### Reuse a session

```python
from rootme_sdk import RootMeClient, Session

with RootMeClient("your-username", "your-password") as client:
    client.session.save(".secrets/session.json")

with RootMeClient(session=Session.load(".secrets/session.json")) as client:
    challenge = client.get_challenge(41)
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
