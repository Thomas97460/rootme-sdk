# Contributing

Use `nix develop`, `uv sync --locked --extra browser`, and `task ci`. Enable the
pre-commit hook with `git config core.hooksPath .githooks`. Automated tests are
offline and independent of Root-Me accounts. Distribution checks prepare locked
runtime dependencies from the local uv cache, install each artifact in a clean
environment and verify public exports, version and typing information.

Branch from current main, open a Conventional Commit PR and squash merge after
checks pass. Required checks are quality (3.13), quality (3.14) and lint-pr-title.
Governance changes and merges touching CODEOWNERS paths require explicit approval
in the conversation, as defined in AGENTS.md.

## Releases

The repository and GitHub releases remain private. PyPI publication is deferred:
the release workflow skips it unless the repository variable PUBLISH_PYPI is true.

1. Set the version in pyproject.toml through a validated PR and merge.
2. Wait for successful CI on that exact main commit.
3. Obtain explicit release approval, then tag that commit as vX.Y.Z and push.
4. Watch release.yml: it verifies version/main CI, checks and builds artifacts,
   then attaches the wheel and source archive to the private GitHub release.
5. Verify assets and install/import each distribution from a clean environment.

Never rewrite release tags or published versions. Correct failures with a normal
PR and a newly approved version/tag.

## Future PyPI setup

Enable PyPI only after explicit authorization and project ownership checks.
Configure a [Pending Trusted Publisher](https://docs.pypi.org/trusted-publishers/creating-a-project-through-oidc/):

- Project: rootme-sdk; confirm name availability and ownership.
- GitHub owner/repository: Thomas97460/rootme-sdk.
- Workflow: release.yml; GitHub environment: pypi.

Create that environment and set PUBLISH_PYPI=true. The workflow uses OIDC without
stored long-lived tokens and publishes the same artifacts as GitHub. Once enabled,
release verification also checks the PyPI version and a clean installation from
PyPI. PyPI artifacts are public even when their source repository remains private.
