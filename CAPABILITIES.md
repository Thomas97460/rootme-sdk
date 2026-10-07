# Capabilities

Authentication uses username/password and reusable web sessions. Official API
reads reuse the login cookie. Website JavaScript gates can affect public reads.

| Client method | Purpose | Access | Evidence |
| --- | --- | --- | --- |
| `RootMeClient(login, password)` / `RootMeClient(credentials_file=...)` | Connect from credentials and manage browser/session internally | Existing account | Both modes observed without human input, including preferences and challenge reads |
| `RootMeClient(..., session_file=...)` | Reuse a saved session and log in only when it is missing or rejected | Existing account | Missing and invalid API sessions answer HTTP 401 (observed 2026-10-07); reuse flow tested offline |
| `login` | Connect/reconnect an existing client, with automatic JS assistance | Existing account | Same managed authentication flow |
| `logout` | Server logout and local credential erasure | Session for server logout | Route observed; behavior tested offline |
| `get_challenge(id)` | Complete website details through the API-provided URL | Login session and website access | API links and challenge pages observed |
| `get_challenge(url)`, `read_challenge` | Full statement, challenge files, named resource URLs and access instructions | Website access | Challenge pages observed |
| `list_challenges`, `iter_challenges` | Filters and pagination | Login session | Documented API; response shapes observed |
| `list_categories` | Catalogue categories | Website access | 11 categories observed |
| `get_user` | Account profile, score and available progression data | Login session | Authenticated profile response observed; validations hold solved entries |
| `preferences` | Editable account field inventory | Web session | modifier_auteur form observed |
| `update_preferences` | Selected profile changes and file uploads | Web session | Controls observed; tested offline |
| `submit_answer` | One answer submission and structured result | Web session | Live already-solved response observed; other outcomes tested offline |
| `download`, `download_files` | Challenge files and resources with scoped credentials | Public or same-host session | Static challenge archives and repository PDFs downloaded live |

## Limits

Password authentication uses only graphical Chrome/Chromium. The SDK finds or
prepares Chromium automatically, waits for native login
completion and verifies the account preferences page before returning a connected
client. A graphical display and Chromium's system dependencies are prerequisites;
missing Linux `DISPLAY` is rejected before browser startup. Headless and HTTP-only
login are not supported. Platform verification, network and rate-limit failures
are explicit errors. Credentials rejected on the login page are not resubmitted.

Authentication is still at alpha maturity. Manual checks reproduced intermittent
account-verification rejection on 2026-10-05. Native login could return positive
feedback, redirect to the news page and provide an account session cookie before
the preferences check failed. These observations do not establish a server-side
cause or demonstrate that credentials were rejected. A failed preferences check
was also followed by an API HTTP 401 using the same cookie: that session was not
accepted by either interface.

Anonymous browser inspection confirmed that changing the login field starts an AJAX
identity lookup. Authentication now blurs that field explicitly and waits for the
lookup to match the supplied login before entering the password. Redirect detection
parses query parameters instead of assuming their order. Form readiness and identity
lookup waits exclude unrelated AJAX and full-page asset loading; each interactive
login step is capped at 10 seconds. Verification waits for the hidden preferences
control to be attached, then refreshes cookies; the previous visibility wait could
only time out and left an earlier cookie snapshot. When a session is present, a
missing account form triggers one more preferences GET, never another login POST.
On 2026-10-06 the rejected sessions were observed as a redirect from preferences
to the login page; that redirect is now an immediate rejection instead of a wait
for the account control, so renewal starts within about a second.
After a native login redirect, an explicitly rejected session is cleared and login
is attempted once more. Persistent denial still raises an authentication error;
missing sessions, credentials rejected on the login page, human verification,
network errors and rate limits do not trigger another login. Offline regressions
cover these cases, including unusable fields and indefinitely active background AJAX.

The final manual check on 2026-10-05 used three fresh credential-based clients.
All three verified account access and read challenge details with six named resource
URLs. Two connected on their first native attempt; the third recovered through the
single session-renewal attempt. This small sample does not establish a success rate
or explain why Root-Me rejected the first session.

Automated unit and packaging checks cannot establish reliable live platform
authentication. Account preference mutations also lack live validation.

Submission feedback is read only inside the challenge validation form, using
observed success/error and SPIP feedback classes. Explicit English/French
already-solved messages are recognized. HTTP 429 is blocked; ambiguous failures
and unknown feedback remain indeterminate. Writes are never automatically replayed.

Root-Me answers request bursts with HTTP 429, sometimes without `Retry-After` and
for several minutes, including on profile and search reads. The client therefore
spaces requests by 2 seconds by default. A field report described persistent 429
responses on one network's IPv4 egress while IPv6 succeeded, so the SDK no longer
binds connections to IPv4. On 2026-10-07, anonymous website and API reads succeeded
over both IPv4 and IPv6, and the default transport selected IPv6 where available.
Changing address family to escape a rate limit is not attempted automatically.

Challenge files are the page links served by `static.root-me.org`. On 2026-10-06,
challenges sampled in every category placed their downloadable material there,
mostly behind the statement's *Download the challenge* button and once as a plain
statement link; related documentation lives in a separate block. Statement links
to other hosts, code-snippet downloads and *Start* buttons are not challenge files.
Some hosted challenges serve a file through their *Start* link on a challenge
server over HTTP; the SDK does not treat or download those as files.

Account updates support one value per control and one file per upload control.
Preference mutations have not been manually exercised. The SDK exposes account
and challenge operations only; generic forms are private implementation details.

Source: [official API documentation](https://api.www.root-me.org/?lang=en) and
manual observations from 2026-10-04 to 2026-10-06. No real answer, credential or account snapshot
is committed in fixtures.
