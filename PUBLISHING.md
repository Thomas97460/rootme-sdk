# Public GitHub and PyPI preparation

The repository remains private and `PUBLISH_PYPI=false`. No publication or
visibility change follows from merging the preparation work. The current package
version is 0.3.0; its tag has not been published.

## Prepared in the repository

- MIT license and SPDX metadata, author, Python support, alpha maturity, typing,
  project links and a README suitable for PyPI rendering.
- Account/challenge API reference, graphical-runtime requirements, migration
  guidance, contribution instructions and a private security contact.
- Offline tests with 100% SDK unit coverage, package guard tests, and wheel/source
  installation checks on Python 3.13/3.14 across Linux, macOS and Windows.
- Runtime dependency advisory checks, redacted secret scanning and weekly updates.
  GitHub Actions are pinned to commits, with minimal job permissions.
- Tag/version/exact-main-CI and security checks, a single validated build shared by GitHub/PyPI,
  OIDC publishing and post-publication hash/clean-install verification.

Before opening, run `task ci`, `task audit` and `task secrets` on the final commit.
Gitleaks covers common secret formats; also compare historical blobs, package
contents and old release assets against locally stored account secrets without
printing them. Changing current files does not remove historical data. Commit
author identities, old docs and release notes become public with the repository;
review those intentionally. Fixtures contain synthetic examples, never copied
challenge statements or real answers.

Preparation audit on 2026-10-04: Gitleaks found no leaks in the existing 10 local
commits; 110 reachable historical blobs and four v0.1.0/v0.2.0 release artifacts
contained no locally known passwords, submitted answer or session cookie values.
The locked runtime dependency audit reported no known vulnerabilities. PyPI's
project API returned 404 for `rootme-sdk`; this is not a name reservation.
These checks are a dated result, not a guarantee about future changes.

## Product maturity decision

Publishing an **alpha** is possible with the current documented limits. Publishing
as a reliable unattended-login SDK is not yet justified: some fresh sessions fail
account verification after positive login feedback, for an unresolved reason.
Preference mutations also have not been tested on a real account. Offline coverage
does not resolve these platform-level limits. Further live tests are intentionally
deferred; do not run repeated logins merely to obtain one successful result.

## Owner actions after deciding to publish

1. Confirm the alpha positioning and choose whether to open the repository.
   Enable GitHub private vulnerability reporting after it becomes public; the
   email contact already works independently. Review main protection rules for
   the quality, portability and security checks before accepting outside changes.
2. In the maintainer's PyPI account, confirm project name availability/ownership
   and create a [Pending Trusted Publisher](https://docs.pypi.org/trusted-publishers/creating-a-project-through-oidc/):
   project **rootme-sdk**, GitHub owner **Thomas97460**, repository **rootme-sdk**,
   workflow **release.yml**, environment **pypi**. A pending publisher does not
   reserve the project name; first successful publication creates the project.
3. Create the GitHub `pypi` environment and explicitly set `PUBLISH_PYPI=true`.
   The workflow skips PyPI while the repository is private, even with that variable
   enabled. No password/token is needed in GitHub for this OIDC publisher.
4. Adjust the README install status through a normal PR. Wait for green CI and
   security checks on its exact main commit. Obtain explicit tag approval, then
   create/push `v0.3.0` on that commit, provided the version remains untagged.
5. Watch the release workflow. It attaches wheel/source assets on GitHub and, when
   enabled, publishes to PyPI. It checks PyPI's exact version file hashes against
   the build and installs that version into a clean environment outside the repo.
   Review both destinations; a successful tag push alone is insufficient.

Never move a tag or replace a published version. If the GitHub publication succeeds
but PyPI fails, repair the workflow through a PR and release a new approved version
instead of blindly replaying all publication jobs. Already uploaded files cannot
be replaced. Never upload credentials or session files as release assets.
