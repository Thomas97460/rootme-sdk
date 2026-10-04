# Security

Report sensitive issues privately to **t.collet974@outlook.fr**. When private
vulnerability reporting is enabled, you can also
[open a private advisory](https://github.com/Thomas97460/rootme-sdk/security/advisories/new).
Never include
account credentials, sessions or submitted answers in public issue reports.

Security fixes target the latest release; older versions are not maintained.
The SDK is currently alpha software, with known authentication limitations
documented in [CAPABILITIES.md](CAPABILITIES.md).

Passwords are used only for an explicit login and are not saved in SDK session
files. Session persistence is opt-in; saved state grants account access. The
client scopes account cookies to the platform website/API and strips them from
external resource requests. Browser assistance uses an isolated browser context.

Credential JSON and session files use UTF-8. Store them outside tracked files
(the documented `.secrets/` directory is ignored). Session saving sets owner-only
permissions on POSIX; on Windows, secure the containing directory through its ACLs.
Do not attach account HTML or raw browser/network logs to reports: platform content
and third-party diagnostic messages can contain secrets. Prefer the SDK exception
type and a sanitized message.

Mutations are not retried automatically. After an ambiguous submission outcome,
the caller should inspect platform state before deliberately submitting again.
