# Agent guidelines — rootme-sdk

## Scope and language

Build the Python library described in [REQUIREMENTS.md](REQUIREMENTS.md). Keep it
small; do not add a server, solver or unrelated application. Choose implementation
details from verified platform behavior rather than guessed endpoints. Scope is
accounts and challenges, with password/session authentication; do not add API-key
authentication, messaging, community or virtual-environment management.

Write repository content in English: code, comments, documentation, commits and
PRs. Speak French with the maintainer. Never add `Co-Authored-By` or other
authorship trailers to commits.

## Python code and architecture

- Use `src/rootme_sdk/`. Start with focused modules and create subpackages only
  when a concern needs multiple modules. Functions stay at most 30 lines; modules
  stay below 1000 lines. Prefer shallow, coherent packages over speculative layers.
- DRY, one concern per module, one intent per code path. Keep code linear and
  avoid abstractions or compatibility branches without a current requirement.
- State responsibility in names. Avoid `utils`, `helpers`, `misc`, `shared`,
  `core`, `base` and `tools` as catch-all module/package names. Shared logic has
  a named owner; do not create a generic `common` tree in advance.
- Define and preserve import direction. Lower-level transport, parsing and
  authentication mechanisms must not depend on the public client orchestrating
  them. No circular imports or unrelated cross-feature dependencies; promote
  genuinely shared logic to its proper owner instead of duplicating it.
- `__init__.py` contains public re-exports and `__all__` only: no logic or
  import-time side effects. Re-export intentional public APIs through the package
  boundary so consumers do not depend on deep implementation imports.
- Type the SDK fully and run `mypy --strict`. Validate caller input and external
  responses at their boundaries, then trust validated data internally. Do not
  hide unexpected defects with broad `try/except`. Expected network, authentication
  and platform failures must become explicit SDK outcomes or documented errors.
- In production code, use `assert` only for type narrowing, never for runtime
  validation or control flow.
- Keep the public interface deliberate and simple. Unlike the source SaaS,
  this library has external consumers: preserve published contracts or make
  breaking changes explicit in the version and migration guidance. Update all
  internal callers and tests in the same change; no speculative legacy paths.
- Keep runtime dependencies minimal. Password authentication manages JavaScript
  assistance and browser setup automatically; callers supply only credentials.
  Browser support is installed by default, but its runtime starts only when
  needed. Do not configure the consuming application's logging or emit secrets.

## Tooling and quality gates

- `pyproject.toml` owns package metadata, the release version, Python support,
  dependencies and tool configuration. Use `uv` and commit `uv.lock`.
- `flake.nix` and `flake.lock` provide a reproducible devShell with Python, `uv`,
  `task`, `gh` and required development tools. Add missing tools there. Do not
  copy Nix package, NixOS/Home Manager module or binary-distribution machinery.
- Provide a small `Taskfile.yml`: formatting, lint, typecheck, docstrings, unit
  tests, package build and an aggregate `task ci`. CI runs the same checks.
- Ruff handles lint and format; line length is 100. Enforce `ruff check` and
  `ruff format --check`, strict mypy, and `interrogate --fail-under=100` for
  applicable SDK docstrings. Use one documented docstring convention.
- Enforce **100% unit-test coverage of the complete SDK** with pytest/pytest-cov
  and `--cov-fail-under=100`, locally and in CI. Broader tests cannot compensate
  for missing unit coverage. Never lower, bypass or remove a quality gate.
- No `pragma: no cover`, `type: ignore`, `noqa`, blanket missing-import ignores,
  coverage exclusions or equivalent escapes without an unavoidable, documented
  constraint. An exception must be narrow and explained beside the suppression.
- Install a `.githooks/` pre-commit hook running `task ci` once tooling exists;
  never bypass it with `--no-verify`. Documentation-only bootstrapping does not
  require implementing the SDK just to validate these initial documents.

## Tests

- Mirror `src/rootme_sdk/` in `tests/unit/`, with one `test_<module>.py` for each
  executable source module. Keep module ownership explicit; delete matching
  tests when deleting a module. Re-export-only files need no artificial tests.
- Test observable behavior and failure cases, including denied access and
  ambiguous submission outcomes. Mock external boundaries rather than the logic
  under test. Fixtures contain no credentials, cookies or real submitted answers.
- All automated tests are offline and independent of a real Root-Me account.
  Add multi-module scenarios or a local fake service when useful, without live
  platform integration. Keep scenarios deterministic, isolated and free of fixed
  sleeps. Do not skip or retry failing tests to obtain green CI.
- Verify built wheels/source distributions install and expose the typed public
  interface without contacting Root-Me. Ship typing information (`py.typed`).

## Git workflow

- Once a remote `main` exists, fetch it and branch from its current state using
  `feat/`, `fix/` or `chore/`. Rebase on `main`; do not merge it into the branch.
  Preserve uncommitted user work. An empty repository needs its initial baseline
  established before the ordinary PR workflow is possible.
- Changes land through PRs targeting `main`; no direct pushes to established
  `main`, force-pushes to `main`, or protection bypasses. Use Conventional Commit
  PR titles and squash merges: `git log main` is the release history; no separate
  generated changelog is required.
- Run `task ci` before committing. Use `gh` to inspect PRs and CI failures; verify
  an old branch has not already merged before adding commits to it. Watch checks
  and fix failures. An ordinary PR may merge once required checks pass, subject
  to the protected-path rule below; monitor the resulting `main` CI run too.
- Use `.github/CODEOWNERS` for `.github/`, `flake.nix`, `AGENTS.md` and
  `SECURITY.md`. Merging changes to listed paths requires explicit human approval
  in the conversation. Prepare and validate the complete change before requesting
  that approval. Live GitHub protection/governance changes also need explicit
  approval; missing permissions are reported rather than worked around.

## Releases

- Distribution is a wheel and source archive attached to a private GitHub
  Release. PyPI publication is deferred and disabled unless explicitly enabled
  with publisher permissions. Merging to `main` does not publish a release.
  Do not add PyInstaller binaries or Nix packaging.
- Bump `[project].version` in `pyproject.toml` through a normal PR **before**
  tagging. Tag the corresponding validated commit on `main` as `vX.Y.Z`; the
  tag, package metadata and artifact versions must agree.
- **Never push a release tag or publish a version without explicit human opt-in
  in the current conversation.** Approval of a release tag authorizes both
  all currently enabled publication destinations, without a second approval.
  Never move or delete an existing release tag.
- The tag-triggered workflow builds and checks the wheel/source archive from
  that commit, then publishes those artifacts to enabled destinations. Configure
  authentication securely; never commit tokens. Confirm PyPI ownership/name
  availability and permissions before enabling its first publication.
- Watch the workflow to completion. Verify both GitHub assets and clean artifact
  installation/import, plus the PyPI version/install when publishing is enabled;
  a successful tag push is not completion.
- Fix failed releases through the normal workflow. Roll forward with a new
  version and tag; consumers can pin a previous known-good version. Never rewrite
  release history. A corrective release still needs explicit tag approval.

## Reference principles

Adapted from `/home/collet/Bureau/quota-tracker/AGENTS.md` for Git/release rules
and `/home/collet/Bureau/llm/llm-saas/AGENTS.md` for relevant Python rules. These
guidelines are self-contained; deployment, frontend, database and Nix packaging
rules from those applications do not apply to this SDK.
