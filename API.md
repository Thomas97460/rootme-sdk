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

The constructor's optional keyword arguments are `timeout=30` (HTTP seconds),
`read_retries=1`, `max_retry_delay=5`, and `transport` (an HTTPX transport, useful
for offline tests). Managed browser login has a separate 180-second timeout;
`login(..., timeout=180)` can change it. Read retries are bounded and respect
eligible waiting intervals; authentication and writes are never replayed.

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
| `get_user(identifier)` | `UserProfile`; `id`, `name`, `score`, `position`, additional JSON in `data` |
| `preferences(language="en")` | `WebPage`; current editable controls in `forms` |
| `update_preferences(changes, files=None)` | `WebPage`; send selected editable fields once, refreshing hidden tokens |
| `get_challenge(id)` | `Challenge`; authenticated API metadata, often without a statement |
| `get_challenge(url)` / `read_challenge(id_or_url)` | `Challenge`; full website statement and resources |
| `list_challenges(title=None, subtitle=None, language=None, score=None, author_ids=())` | `Collection[Challenge]`; one API page, with `items` and `next_url`; all filters are keyword-only |
| `iter_challenges(**filters)` | `Iterator[Challenge]`; lazy pagination with native API filter names, such as `lang="en"`, `score=5`, `titre="..."` |
| `list_categories(language="en")` | `tuple[Category, ...]`; category `title` and `url` |
| `submit_answer(id_or_url, answer)` | `SubmissionResult`; status, sanitized feedback and optional retry interval |
| `download(resource_or_https_url, destination=None)` | `bytes`; optionally write to the supplied path; external hosts receive no account cookies |

Language arguments on website methods are keyword-only and accept `en` or `fr`.
API IDs must be positive integers. `Challenge` exposes `id`, `title`, `score`,
`category_id`, `url`, `statement`, `statement_html`, `resources` and `data`.
API fields absent from a response remain `None`; `.data` preserves extra JSON.
Resources contain a `url` and `label`, including links to services and documentation;
choose downloadable attachments rather than passing arbitrary service links.

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
| `RateLimitedError` | Platform rate limit; `retry_after` can be absent |
| `PermissionDeniedError` | Access denied |
| `NotFoundError` | Requested resource absent |
| `NetworkError` | Network operation failed |
| `UnexpectedResponseError` | Unrecognized or invalid platform response |

See [CAPABILITIES.md](CAPABILITIES.md) for live observations and unresolved limits.
