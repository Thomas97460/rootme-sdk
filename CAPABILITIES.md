# Capabilities

API data access and website-account access are separate capabilities. An API key
is sufficient for documented API reads; website mutations need a web session.
Anubis or another browser gate can affect public website reads too.

| Client method | Purpose | Access | Evidence |
| --- | --- | --- | --- |
| `login` | Password or secret-file login, optionally in a browser | Existing account | Fresh supplied-password browser login observed without human input |
| `open_browser` | Manual/automatic login and JS website requests | Account, or anonymous with `authenticate=False` | Visible automatic login and headless saved-session reuse observed |
| `logout` | Server logout and local credential erasure | Web session for server logout | Logout route observed; behavior tested offline |
| `get_challenge(id)` | Metadata and extra API fields | API key or session | API detail response observed |
| `get_challenge(url)`, `read_challenge` | Statement, links and resource/access instructions | Website access | Challenge page and parsing observed |
| `list_challenges`, `iter_challenges` | Filters and server pagination | API key or session | API documented; response/pagination shapes observed |
| `list_categories` | Catalogue category links | Website access | Root base element/category links observed |
| `list_users`, `iter_users`, `get_user` | Profiles, score and available solved-challenge data | API key or session | API documented; indexed user response observed |
| `ranking`, `iter_ranking` | Rankings and pagination | API key or session | API documented; tested offline |
| `list_environments`, `iter_environments`, `get_environment` | Virtual-environment metadata | API key or session | API documented; tested offline |
| `get_page` | Text, links and current named forms on any platform page | As required by the page | Authenticated pages observed |
| `preferences` | Profile/preferences field inventory | Web session | `modifier_auteur` form observed |
| `update_preferences` | Explicit profile changes and avatar/CV file uploads | Web session | Controls observed; multipart behavior tested offline |
| `submit_form` | Other discovered account/community/environment forms | Web session for writes | SPIP hidden tokens/control shapes observed |
| `perform_action` | Discovered action links, including GET mutations | Web session | Action links observed; no automatic retries |
| `submit_answer` | One answer submission with conservative outcome classification | Web session | `validation_challenge`/`passe` observed; outcomes tested offline |
| `download` | Binary attachments without leaking credentials to other hosts | Public or same-host web session | Transport behavior tested offline |

## Limits

The official API does not document answer submission or general account writes.
Generic form discovery exposes the controls actually present, rather than guessed
forum/private-message/environment endpoints. One value per control name and one
file per upload control are supported; multiple-select/repeated-value workflows
and arbitrary JavaScript-only buttons need an explicit adapter once observed.
The library does not claim to implement every feature hidden behind those buttons.

A fresh visible-browser login succeeded with supplied credentials and no human
input; the saved session was then reused headlessly. A fresh headless login was
blocked by Anubis in this environment. API-key reads do not need a browser;
password-only HTTP login can encounter the site's JavaScript gate.

Submission success/rejection is read from SPIP's validation feedback classes,
never from HTTP 200 alone. Explicit English/French already-solved feedback is
recognized. HTTP 429 is blocked; unknown/localized feedback and ambiguous network
or redirect outcomes remain indeterminate. These classifications have not yet
been confirmed by real submissions. Forms/action links can change as Root-Me evolves.

Source: [official API documentation](https://api.www.root-me.org/?lang=en) and
manual read-only observation on 2026-10-04. No private page, API key, cookie or
real answer appears in the committed fixtures.
