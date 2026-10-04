# Contributing

Use `nix develop`, `uv sync --locked --extra browser`, and `task ci`. Enable the
pre-commit hook with `git config core.hooksPath .githooks`. Tests are offline; do
not add account credentials or real platform calls to CI. Build verification
installs the wheel and source archive into clean environments using the local uv
cache, checks the public exports and confirms the typing marker is included.

Branch from current `main`, open a PR with a Conventional Commit title and squash
merge only after required checks pass. Set the repository's required checks to
`quality (3.13)`, `quality (3.14)` and `lint-pr-title` for PRs. Repository settings
and protection changes require the maintainer's explicit approval. A change to a
CODEOWNERS path also needs conversational approval before merging; do not require
self-approval through GitHub review, which cannot be satisfied by the author.

## Release setup

Before the first approved release, configure a pending
[PyPI Trusted Publisher](https://docs.pypi.org/trusted-publishers/creating-a-project-through-oidc/):

- Project: `rootme-sdk` (confirm name availability and ownership).
- GitHub owner: `Thomas97460`; repository: `rootme-sdk`.
- Workflow: `release.yml`; GitHub environment: `pypi`.

Create the corresponding GitHub environment. The workflow exchanges its OIDC
identity for a short-lived PyPI credential; no long-lived token is stored in the
repository. A PyPI project lookup returned 404 on 2026-10-04; that does not
guarantee the name can still be registered when publishing.

## Release procedure

1. Update `[project].version` in a normal PR, validate and merge.
2. Wait for successful CI on that exact `main` commit.
3. Obtain explicit approval for `vX.Y.Z` in the current conversation, then tag
   and push that validated commit. This approves both publication destinations.
4. Watch `release.yml`: it checks tag/version/main CI, builds and verifies the
   artifacts once, then sends identical files to GitHub and PyPI.
5. Confirm both GitHub assets, PyPI metadata and installation/import from PyPI
   in a clean environment. No release is complete before those checks succeed.

Never rewrite release tags or an existing package version. Correct failures by
fixing forward through a PR and a newly approved version/tag. A partial publication
must be diagnosed; it is not a successful release. Consumers can pin a previous
known-good version while the correction is prepared.
