# Contributing

Use `nix develop`, `uv sync --locked`, and `task ci`. Enable the
pre-commit hook with `git config core.hooksPath .githooks`. Automated tests are
offline and independent of Root-Me accounts. Distribution checks prepare locked
runtime dependencies from the local uv cache, install each artifact in a clean
environment and verify public exports, version and typing information.

Branch from current main, open a Conventional Commit PR and squash merge after
checks pass. Required checks are quality (3.13), quality (3.14) and lint-pr-title.
Also wait for Windows/macOS portability, dependency audit and secret scan checks.
Governance changes and merges touching CODEOWNERS paths require explicit approval
in the conversation, as defined in AGENTS.md.

## Without Nix

Install Python 3.13 or 3.14, [uv](https://docs.astral.sh/uv/getting-started/installation/)
and [Task](https://taskfile.dev/docs/installation), then run the same `uv sync --locked`
and `task ci` commands. Nix is only a development environment, never a runtime
requirement. Use Google-style docstrings and the self-contained [AGENTS.md](AGENTS.md)
coding rules. The public API reference is [API.md](API.md).

`task ci` includes offline packaging guard tests. Run `task audit` separately to
check the locked runtime dependencies against published vulnerability advisories
(network access required). Run `task secrets` with Gitleaks installed to scan the
complete local Git history with redacted findings. Both tools are in the devShell;
security CI repeats these checks weekly and on changes. Dependency updates arrive
as ordinary Dependabot PRs and must pass the same checks.

## Releases

The repository and GitHub releases are public. PyPI publication is deferred:
the release workflow skips it unless the repository variable PUBLISH_PYPI is true.

1. Set the version in pyproject.toml through a validated PR and merge.
2. Wait for successful CI on that exact main commit.
3. Obtain explicit release approval, then tag that commit as vX.Y.Z and push.
4. Watch release.yml: it verifies version/main CI, checks and builds artifacts,
   then attaches the wheel and source archive to the GitHub release.
5. Verify assets and install/import each distribution from a clean environment.

Never rewrite release tags or published versions. Correct failures with a normal
PR and a newly approved version/tag.

## Future PyPI setup

Enable PyPI only after explicit authorization and project ownership checks.
Configure a [Pending Trusted Publisher](https://docs.pypi.org/trusted-publishers/creating-a-project-through-oidc/):

- Project: rootme-sdk; confirm name availability and ownership.
- GitHub owner/repository: Thomas97460/rootme-sdk.
- Workflow: release.yml; GitHub environment: pypi.

After the decision to open the repository, create that environment and set
PUBLISH_PYPI=true. The workflow uses OIDC without
stored long-lived tokens and publishes the same artifacts as GitHub. Once enabled,
release verification also checks the PyPI version and a clean installation from
PyPI. This repository's workflow also requires public repository visibility.
See [PUBLISHING.md](PUBLISHING.md) for the remaining owner actions and release procedure.
