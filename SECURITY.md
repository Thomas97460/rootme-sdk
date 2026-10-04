# Security

Report sensitive issues privately to the repository maintainer. Never include
account credentials, sessions or submitted answers in public issue reports.

Passwords are used only for an explicit login and are not saved in SDK session
files. Session persistence is opt-in; saved state grants account access. The
client scopes account cookies to the platform website/API and strips them from
external resource requests. Browser assistance uses an isolated browser context.

Mutations are not retried automatically. After an ambiguous submission outcome,
the caller should inspect platform state before deliberately submitting again.
