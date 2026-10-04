"""The small public facade combining official API reads and discovered web forms."""

from __future__ import annotations

from collections.abc import Callable, Iterator, Mapping, Sequence
from pathlib import Path
from types import TracebackType
from typing import Self
from urllib.parse import parse_qs, urlsplit

import httpx

from .authentication.session import API_HOST, WEB_HOST, Session, SessionCookie
from .errors import (
    AuthenticationRequiredError,
    NetworkError,
    RateLimitedError,
    UnexpectedResponseError,
)
from .models import (
    Category,
    Challenge,
    Collection,
    JSONObject,
    JSONValue,
    Resource,
    SubmissionResult,
    SubmissionStatus,
    Upload,
    UserProfile,
    WebForm,
    WebPage,
)
from .parsers import api, web
from .transport import Query, Transport
from .urls import platform_url

API_URL = f"https://{API_HOST}"
WEB_URL = f"https://{WEB_HOST}"


class RootMeClient:
    """A synchronous Root-Me client owning its HTTP pool and optional browser."""

    def __init__(
        self,
        *,
        spip_session: str | None = None,
        session: Session | None = None,
        transport: httpx.BaseTransport | None = None,
        timeout: float = 30,
        read_retries: int = 1,
        max_retry_delay: float = 5,
    ) -> None:
        """Accept a reusable login session; construction performs no requests."""
        if session is not None and spip_session is not None:
            raise ValueError("Supply a session or credentials, not both.")
        cookies = (SessionCookie("spip_session", spip_session),) if spip_session else ()
        self.session = session or Session(cookies=cookies)
        self._transport = Transport(
            self.session,
            transport=transport,
            timeout=timeout,
            read_retries=read_retries,
            max_retry_delay=max_retry_delay,
        )

    def __enter__(self) -> Self:
        """Enter the owned resource scope."""
        return self

    def __exit__(
        self,
        kind: type[BaseException] | None,
        error: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Close the client even when a caller operation fails."""
        self.close()

    def close(self) -> None:
        """Release all owned network and browser resources."""
        self._transport.close()

    def login(
        self,
        username: str,
        password: str | None = None,
        *,
        password_file: str | Path | None = None,
        browser: bool = False,
        executable_path: str | None = None,
        headless: bool = False,
        timeout: float = 180,
    ) -> Session:
        """Log in with an in-memory password or local secret file, optionally using JS."""
        secret = _password(username, password, password_file)
        self.session.cookies = tuple(c for c in self.session.cookies if c.name != "spip_session")
        if browser:
            return self.open_browser(
                username=username,
                password=secret,
                executable_path=executable_path,
                headless=headless,
                timeout=timeout,
            )
        return self._http_login(username, secret)

    def open_browser(
        self,
        *,
        username: str | None = None,
        password: str | None = None,
        executable_path: str | None = None,
        headless: bool = False,
        timeout: float = 180,
        authenticate: bool = True,
    ) -> Session:
        """Explicitly authenticate in a browser and retain it for website operations."""
        from .authentication.browser import BrowserSession

        if self._transport.browser:
            self._transport.browser.close()
            self._transport.browser = None
        browser = BrowserSession(
            self.session, executable_path=executable_path, headless=headless, timeout=timeout
        )
        try:
            result = browser.authenticate(username, password) if authenticate else browser.prepare()
        except Exception:
            browser.close()
            raise
        self._transport.browser = browser
        return result

    def logout(self) -> None:
        """Invalidate the web session when present, then always erase local credentials."""
        try:
            if self.session.spip_session:
                self._transport.request("GET", f"{WEB_URL}/?action=logout", mutation=True)
        finally:
            self.session.cookies = ()
            if self._transport.browser:
                self._transport.browser.close()
                self._transport.browser = None

    def get_challenge(self, reference: int | str) -> Challenge:
        """Read API metadata by ID, or a complete web challenge by its URL."""
        if isinstance(reference, str):
            return web.challenge_page(self._get_page(reference))
        _identifier(reference)
        data = self._one(f"/challenges/{reference}")
        return api.challenge(data, identifier=reference)

    def read_challenge(self, reference: int | str) -> Challenge:
        """Read the statement and resources, resolving an API ID to its actual URL."""
        url = self._challenge_url(reference)
        return web.challenge_page(self._get_page(url))

    def list_challenges(
        self,
        *,
        title: str | None = None,
        subtitle: str | None = None,
        language: str | None = None,
        score: int | None = None,
        author_ids: Sequence[int] = (),
    ) -> Collection[Challenge]:
        """Read one page using only filters documented by the official API."""
        params = _query({"titre": title, "soustitre": subtitle, "lang": language, "score": score})
        for identifier in author_ids:
            _identifier(identifier)
        pairs = list(params.multi_items()) + [("id_auteur[]", str(i)) for i in author_ids]
        return self._collection(
            f"{API_URL}/challenges", api.challenge, httpx.QueryParams(tuple(pairs))
        )

    def iter_challenges(self, **filters: str | int) -> Iterator[Challenge]:
        """Iterate server-provided catalogue pages using native API filter names."""
        yield from self._iterate(f"{API_URL}/challenges", api.challenge, filters)

    def get_user(self, identifier: int) -> UserProfile:
        """Read a profile, including the platform's solved-challenge data."""
        _identifier(identifier)
        return api.user(self._one(f"/auteurs/{identifier}"), identifier=identifier)

    def list_categories(self, *, language: str = "en") -> tuple[Category, ...]:
        """Discover category links from the live challenge catalogue."""
        _language(language)
        document = self._get_page(f"{WEB_URL}/{language}/Challenges/")
        prefix = f"/{language}/Challenges/"
        return tuple(
            Category(link.label, link.url)
            for link in document.links
            if urlsplit(link.url).hostname == WEB_HOST
            and urlsplit(link.url).path.startswith(prefix)
            and len(urlsplit(link.url).path[len(prefix) :].strip("/").split("/")) == 1
            and urlsplit(link.url).path != prefix
            and link.label
        )

    def _get_page(self, url: str) -> WebPage:
        """Read an anonymous or authenticated page and discover its forms and links."""
        if urlsplit(platform_url(url)).hostname != WEB_HOST:
            raise ValueError("Website pages must use the website host.")
        if "action" in parse_qs(urlsplit(url).query):
            raise ValueError("Action links cannot be used for page reads.")
        response = self._transport.request("GET", url)
        return web.page(response.text, str(response.url))

    def preferences(self, *, language: str = "en") -> WebPage:
        """Read editable profile/preferences controls without changing anything."""
        _language(language)
        if not self.session.spip_session:
            raise AuthenticationRequiredError("Preferences require a web session.")
        document = self._get_page(f"{WEB_URL}/?page=preferences&lang={language}")
        _find_form(document, "modifier_auteur")
        return document

    def update_preferences(
        self, changes: Mapping[str, str], *, files: Mapping[str, Upload] | None = None
    ) -> WebPage:
        """Explicitly update fields exposed by the verified modifier_auteur form."""
        form = _find_form(self.preferences(), "modifier_auteur")
        return self._submit_form(form, changes, files=files)

    def _submit_form(
        self,
        form: WebForm,
        changes: Mapping[str, str],
        *,
        files: Mapping[str, Upload] | None = None,
    ) -> WebPage:
        """Refresh tokens and submit one explicitly chosen form, including file uploads."""
        current = _find_form(self._get_page(form.page_url), form.name)
        values = web.form_values(current, changes)
        allowed = {f.name for f in current.fields if f.kind == "file"}
        if files and not set(files).issubset(allowed):
            raise ValueError("Unknown file upload control.")
        uploads = {
            name: (file.filename, file.content, file.content_type)
            for name, file in (files or {}).items()
        }
        options = {"params": values} if current.method == "GET" else {"data": values}
        response = self._transport.request(
            current.method,
            current.action,
            **options,
            files=uploads or None,
            mutation=True,
            authenticated=current.name != "login",
        )
        return web.page(response.text, str(response.url))

    def submit_answer(self, reference: int | str, answer: str) -> SubmissionResult:
        """Submit exactly once and report uncertainty rather than replaying an answer."""
        if not answer:
            raise ValueError("An answer must be nonempty.")
        document = self._get_page(self._challenge_url(reference))
        known = web.submission_result(document, answer)
        if known.status == SubmissionStatus.ALREADY_SOLVED:
            return known
        form = _find_form(document, "validation_challenge")
        try:
            result = self._submit_form(form, {"passe": answer})
        except RateLimitedError as error:
            return SubmissionResult(SubmissionStatus.BLOCKED, retry_after=error.retry_after)
        except (NetworkError, UnexpectedResponseError):
            return SubmissionResult(SubmissionStatus.INDETERMINATE)
        return web.submission_result(result, answer)

    def download(self, resource: Resource | str, destination: str | Path | None = None) -> bytes:
        """Download a public HTTPS attachment without account credentials."""
        data = self._transport.download(
            resource.url if isinstance(resource, Resource) else resource
        )
        if destination is not None:
            Path(destination).write_bytes(data)
        return data

    def _challenge_url(self, reference: int | str) -> str:
        """Resolve a challenge reference without constructing an unverified web route."""
        if isinstance(reference, str):
            return platform_url(reference)
        result = self.get_challenge(reference)
        if not result.url:
            raise UnexpectedResponseError("API did not provide a challenge URL.")
        return platform_url(result.url)

    def _http_login(self, username: str, password: str) -> Session:
        """Verify password authentication against the returned account menu."""
        document = self._get_page(f"{WEB_URL}/?page=login&lang=en")
        form = _find_form(document, "login")
        result = self._submit_form(form, {"var_login": username, "password": password})
        logged_in = any(
            parse_qs(urlsplit(link.url).query).get("action") == ["logout"] for link in result.links
        )
        if not self.session.spip_session or not logged_in:
            raise AuthenticationRequiredError(
                "Login did not produce an authenticated session.", reason="rejected"
            )
        return self.session

    def _one(self, path: str) -> JSONObject:
        """Require exactly one data record in a detail response."""
        data = api.records(self._api(f"{API_URL}{path}"))
        if len(data) != 1:
            raise UnexpectedResponseError("Expected one API detail record.")
        return data[0]

    def _api(self, url: str, params: Query | None = None) -> JSONValue:
        """Read and validate JSON from the exact official API host."""
        if urlsplit(platform_url(url)).hostname != API_HOST:
            raise UnexpectedResponseError("API continuation points outside the API.")
        response = self._transport.request("GET", url, params=params, authenticated=True)
        return api.json_payload(response.text)

    def _collection[T](
        self, url: str, parse: Callable[[JSONObject], T], params: Query | None = None
    ) -> Collection[T]:
        """Preserve the server's continuation link alongside parsed records."""
        data = self._api(url, params)
        values = data if isinstance(data, list) else [data]
        next_url = next(
            (
                str(v["href"])
                for v in values
                if isinstance(v, dict) and v.get("rel") == "next" and isinstance(v.get("href"), str)
            ),
            None,
        )
        return Collection(tuple(parse(record) for record in api.records(data)), next_url)

    def _iterate[T](
        self, url: str, parse: Callable[[JSONObject], T], params: Query | None = None
    ) -> Iterator[T]:
        """Follow server pagination lazily, rejecting cycles and untrusted hosts."""
        seen = set()
        while url:
            if url in seen:
                raise UnexpectedResponseError("API pagination cycle detected.")
            seen.add(url)
            result = self._collection(url, parse, params)
            yield from result.items
            url, params = result.next_url or "", None


def _password(username: str, password: str | None, path: str | Path | None) -> str:
    """Read a local secret with one terminal newline removed, never retaining its path."""
    if not username or (password is None) == (path is None):
        raise ValueError("Supply a username and exactly one password source.")
    result = Path(path).read_text().removesuffix("\n").removesuffix("\r") if path else password
    if not result:
        raise ValueError("Password must be nonempty.")
    return result


def _find_form(document: WebPage, name: str) -> WebForm:
    """Resolve a current form by its observed SPIP action or HTML identifier."""
    matches = [form for form in document.forms if form.name == name]
    if len(matches) == 1:
        return matches[0]
    if any(form.name == "login" for form in document.forms):
        raise AuthenticationRequiredError(
            "Page requires an authenticated web session.", reason="rejected"
        )
    raise UnexpectedResponseError("Expected form is missing or ambiguous.")


def _identifier(identifier: int) -> None:
    """Reject nonpositive IDs, including booleans masquerading as integers."""
    if type(identifier) is not int or identifier <= 0:
        raise ValueError("Identifier must be a positive integer.")


def _language(language: str) -> None:
    """Validate a simple platform language code at the caller boundary."""
    if len(language) != 2 or not language.isascii() or not language.isalpha():
        raise ValueError("Language must be a two-letter code.")


def _query(values: Mapping[str, str | int | None]) -> httpx.QueryParams:
    """Omit absent API filters without dropping zero-valued filters."""
    return httpx.QueryParams({key: value for key, value in values.items() if value is not None})
