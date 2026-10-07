# Public API

Import supported names from `rootme_sdk`, not its internal submodules. This is a
synchronous SDK. Use one client in one thread and close it with a `with` block.
Its synchronous Playwright browser cannot run in a thread with an active asyncio
event loop; call the whole client lifecycle from a separate synchronous worker
when embedding it in an asynchronous application.

## Connection

```python
from rootme_sdk import RootMeClient

with RootMeClient("your-login", "your-password") as client:
    page = client.list_challenges(language="en", score=5)
    for challenge in page.items:
        print(challenge.id, challenge.title)
```

Alternatively, `RootMeClient(credentials_file=".secrets/credentials.json")` reads
`{"login": "...", "password": "..."}` as UTF-8. Supply exactly one credential
source. An anonymous `RootMeClient()` can read website challenge URLs and categories;
an ID must first resolve through the authenticated API. Anonymous reads may still
open a graphical browser for JavaScript verification.

`session_file=".secrets/session.json"` adds a reusable session to supplied credentials.
The client first loads that file and checks it with one profile read. Only a missing,
invalid or locally expired file, or an `AuthenticationRequiredError` from that check,
starts a password login; rate limits, network failures and other errors propagate
without logging in. The file is written after that login and when the client closes
with a valid session, and `logout()` deletes it. Its parent directory must exist.

The constructor's optional keyword arguments are `timeout=30` (HTTP seconds),
`read_retries=1`, `max_retry_delay=5`, `min_request_interval=2` (minimum seconds
between the starts of consecutive platform requests, including retries and downloads;
`0` disables pacing) and `transport` (an HTTPX transport, useful for offline tests or
to bind a local address such as `httpx.HTTPTransport(local_address="::")`). The
default transport leaves IPv4/IPv6 selection to the system. Managed browser login has a separate 180-second timeout;
`login(..., timeout=180)` can change it. Read retries are bounded and respect
eligible waiting intervals; ambiguous authentication attempts and writes are never replayed.
During login, the SDK waits only for the form's initialization and the username's
identity lookup, without waiting for unrelated page assets or background AJAX.
Each interactive login step (form readiness, identity lookup, field entry, submission
and account check) is capped at 10 seconds (or the shorter browser timeout), with
separate errors for readiness, identity and field entry.
It checks account access through the hidden preferences form and captures
the final cookies. A redirect from preferences to the login page is an immediate
rejection; if a session is present but that form is otherwise missing, it retries
only the preferences GET once. Network errors and rate limits propagate immediately.
If native login redirected away from the form but the resulting session is
explicitly rejected, the SDK removes only that session cookie and tries login
once more. A persistent rejection, missing session, credentials rejected on the
login page, human verification or an ambiguous network error stops authentication.

Advanced session reuse accepts `session=Session.load(path)` or
`spip_session="..."` instead of login credentials. These contain account secrets,
do not renew expired sessions and do not eliminate later JavaScript verification.
Ordinary users need only credentials. `client.session.save(path)` is opt-in.

## Account and challenges

| Method | Result and behavior |
| --- | --- |
| `login(username, password)` or `login(credentials_file=...)` | `Session`; authenticate/reconnect using the graphical browser |
| `logout()` | `None`; request server logout, clear local state and close the browser |
| `close()` | `None`; release browser and HTTP resources |
| `search_challenges(query=None, category=None, difficulty=None, score=None, limit=10)` | `Iterator[ChallengeSummary]`; search challenges by title, category enum, difficulty enum, or score |
| `get_challenge(id_or_url)` / `read_challenge(id_or_url)` | `Challenge`; flat challenge details, statement, authors, difficulty, files and resources |
| `submit_flag(challenge_id, flag)` / `submit_answer(id_or_url, answer)` | `SubmissionResult`; status (`ACCEPTED`, `REJECTED`, `ALREADY_SOLVED`), sanitized message and retry interval |
| `get_profile(user_id=None)` | `UserProfile`; flat account profile (`id`, `username`, `score`, `rank`, `solved_challenges_count`) |
| `get_user(identifier)` | `UserProfile`; read profile by numeric account ID |
| `preferences(language="en")` | `WebPage`; current editable controls in `forms` |
| `update_preferences(changes, files=None)` | `WebPage`; send selected editable fields once, refreshing hidden tokens |
| `list_challenges(title=None, subtitle=None, language=None, score=None, author_ids=(), **extra_filters)` | `Collection[Challenge]`; one raw API page, with `items` and `next_url` |
| `iter_challenges(title=None, subtitle=None, language=None, score=None, author_ids=(), **extra_filters)` | `Iterator[Challenge]`; lazy pagination across all pages using raw filters |
| `list_categories(language="en")` | `tuple[Category, ...]`; all supported category enums |
| `download(resource_or_https_url, destination=None)` | `bytes`; optionally write to the supplied file path, or into an existing directory under the URL's file name; external hosts receive no account cookies |
| `download_files(challenge_or_id_or_url, directory=".")` | `tuple[Path, ...]`; write every challenge file into `directory` (created if missing) under its URL file name, overwriting existing files |

Language arguments on website methods are keyword-only and accept `en` or `fr`.
API IDs must be positive integers. `Challenge` exposes `id`, `title`, `score`,
`category_id`, `url`, `statement`, `statement_html`, `files`, `resources`, `data` and
`instance_url`.
API fields absent from a response remain `None`; `.data` preserves extra JSON.

`files` and `resources` are both tuples of `Resource` (`url`, `label`, `filename`)
but hold different things. `files` is the challenge's own material: links served by
`static.root-me.org`, usually the statement's *Download the challenge* button.
`resources` holds every other link: documentation and references Root-Me associates
with the challenge, and other statement links. Start buttons for hosted instances
appear in neither: their target is `instance_url` (`None` without a web instance, e.g.
SSH challenges, whose connection details are in the statement). Relative links are resolved against the page's HTML base URL,
preserving query parameters and fragments. `Resource.filename` is the decoded last
URL path segment and raises `ValueError` when it cannot safely name a local file.

```python
challenge = client.get_challenge(41)
client.download_files(41)  # ch1.zip in the current directory
for resource in challenge.resources:
    print(resource.label, resource.url)
```

Before 0.5.0, challenge files were listed in `resources`; read them from `files`.

`WebPage` contains `url`, `title`, `text`, `html`, `links` and `forms`.
Each `WebForm` exposes its name and typed `FormField` controls. Account updates
support one string per editable control and `Upload(filename, content, content_type)`
for observed upload controls. Hidden tokens cannot be overridden.

`SubmissionStatus` values are `ACCEPTED`, `REJECTED`, `ALREADY_SOLVED`, `BLOCKED`
and `INDETERMINATE`. After an indeterminate outcome, inspect account/challenge state
before deliberately submitting again. Never turn it into an automatic retry loop.

## Errors

All SDK operational exceptions inherit from `RootMeError`. Invalid caller input
raises `ValueError`; local destination/session file failures can raise `OSError`.

| Exception | Meaning |
| --- | --- |
| `AuthenticationRequiredError` | Login required or rejected; `reason` is `missing`, `expired` or `rejected` |
| `BrowserUnavailableError` | Missing graphical display or browser startup failure |
| `HumanInterventionRequiredError` | Platform verification unresolved; includes `url` |
| `RateLimitedError` | Platform rate limit; `retry_after` (seconds) can be absent and is also stated in the message |
| `PermissionDeniedError` | Access denied |
| `NotFoundError` | Requested resource absent |
| `NetworkError` | Network operation failed |
| `UnexpectedResponseError` | Unrecognized or invalid platform response |

See [CAPABILITIES.md](CAPABILITIES.md) for live observations and unresolved limits.
