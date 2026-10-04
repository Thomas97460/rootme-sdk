# Capabilities

Authentication uses username/password and reusable web sessions. Official API
reads reuse the login cookie. Website JavaScript gates can affect public reads.

| Client method | Purpose | Access | Evidence |
| --- | --- | --- | --- |
| `login` | Password or secret-file login, optionally in a browser | Existing account | Fresh supplied-password browser login observed without human input |
| `open_browser` | Explicit JS assistance or manual login | Account, or anonymous with `authenticate=False` | Visible automatic login and headless session reuse observed |
| `logout` | Server logout and local credential erasure | Session for server logout | Route observed; behavior tested offline |
| `get_challenge(id)` | Metadata and additional API fields | Login session | Detail response observed |
| `get_challenge(url)`, `read_challenge` | Full statement, resources and access instructions | Website access | Challenge pages observed |
| `list_challenges`, `iter_challenges` | Filters and pagination | Login session | Documented API; response shapes observed |
| `list_categories` | Catalogue categories | Website access | 11 categories observed |
| `get_user` | Account profile, score and available progression data | Login session | Authenticated profile response observed; validations hold solved entries |
| `preferences` | Editable account field inventory | Web session | modifier_auteur form observed |
| `update_preferences` | Selected profile changes and file uploads | Web session | Controls observed; tested offline |
| `submit_answer` | One answer submission and structured result | Web session | Live already-solved response observed; other outcomes tested offline |
| `download` | Attachments with scoped credentials | Public or same-host session | Tested offline |

## Limits

A fresh visible-browser login succeeded without human input; the saved session
then worked headlessly. A fresh headless login encountered Anubis in this
environment. HTTP-only password login can encounter the same JavaScript gate.

Submission feedback is read only inside the challenge validation form, using
observed success/error and SPIP feedback classes. Explicit English/French
already-solved messages are recognized. HTTP 429 is blocked; ambiguous failures
and unknown feedback remain indeterminate. Writes are never automatically replayed.

Account updates support one value per control and one file per upload control.
Preference mutations have not been manually exercised. The SDK exposes account
and challenge operations only; generic forms are private implementation details.

Source: [official API documentation](https://api.www.root-me.org/?lang=en) and
manual observations on 2026-10-04. No real answer, credential or account snapshot
is committed in fixtures.
