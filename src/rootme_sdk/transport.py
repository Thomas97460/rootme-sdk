"""Bounded HTTP requests, conservative retries and per-host cookie isolation."""

from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from time import sleep
from typing import TYPE_CHECKING
from urllib.parse import urljoin, urlsplit

import httpx

from .authentication.session import WEB_HOST, Session, SessionCookie
from .errors import (
    AuthenticationRequiredError,
    HumanInterventionRequiredError,
    NetworkError,
    NotFoundError,
    PermissionDeniedError,
    RateLimitedError,
    UnexpectedResponseError,
)
from .urls import platform_url

if TYPE_CHECKING:
    from .authentication.browser import BrowserSession

type Query = Mapping[str, str | int] | httpx.QueryParams
type Files = Mapping[str, tuple[str, bytes, str]]


def retry_after(value: str | None) -> float | None:
    """Parse both seconds and HTTP-date Retry-After values."""
    if value is None:
        return None
    try:
        return max(0, float(value))
    except ValueError:
        try:
            return max(0, (parsedate_to_datetime(value) - datetime.now(UTC)).total_seconds())
        except (ValueError, TypeError, OverflowError):
            return None


def check_response(response: httpx.Response) -> None:
    """Classify status and browser gates without disclosing server content."""
    content = response.text.lower()
    if "anubis_challenge" in content or "anubis_version" in content or "cf-chl-" in content:
        raise HumanInterventionRequiredError(str(response.url.copy_with(query=None)))
    if response.status_code == 401:
        raise AuthenticationRequiredError(
            "Authentication required or session expired.", reason="rejected"
        )
    if response.status_code == 403:
        raise PermissionDeniedError("Root-Me denied access.")
    if response.status_code == 404:
        raise NotFoundError("Root-Me resource not found.")
    if response.status_code == 429:
        raise RateLimitedError(retry_after(response.headers.get("retry-after")))
    if response.is_error:
        raise UnexpectedResponseError(f"Unexpected Root-Me HTTP status {response.status_code}.")


class Transport:
    """An HTTP boundary owning its pool and the caller's isolated session."""

    def __init__(
        self,
        session: Session,
        *,
        transport: httpx.BaseTransport | None = None,
        timeout: float = 30,
        read_retries: int = 1,
        max_retry_delay: float = 5,
        wait: Callable[[float], None] = sleep,
    ) -> None:
        """Create bounded transport; retries apply only to GET requests."""
        if timeout <= 0 or read_retries < 0 or max_retry_delay < 0:
            raise ValueError("Invalid timeout or retry configuration.")
        self.session = session
        self.read_retries, self.max_retry_delay, self.wait = read_retries, max_retry_delay, wait
        self.browser: BrowserSession | None = None
        self.http = httpx.Client(transport=transport, timeout=timeout, trust_env=False)

    def close(self) -> None:
        """Close the owned HTTP connection pool."""
        self.http.close()
        if self.browser:
            self.browser.close()
            self.browser = None

    def request(
        self,
        method: str,
        url: str,
        *,
        data: Mapping[str, str] | None = None,
        params: Query | None = None,
        authenticated: bool = False,
        files: Files | None = None,
        mutation: bool = False,
    ) -> httpx.Response:
        """Request a platform page, following safe redirects without replaying writes."""
        platform_url(url)
        self._require_auth(authenticated)
        for _ in range(6):
            response = self._read_retry(method, url, data, params, files, mutation)
            self._remember(response)
            if not response.is_redirect:
                check_response(response)
                return response
            url = platform_url(urljoin(str(response.url), response.headers.get("location", "")))
            if method != "GET" and response.status_code not in {301, 302, 303}:
                raise UnexpectedResponseError("Refusing to replay a mutation after a redirect.")
            method, data, params, files = "GET", None, None, None
        raise UnexpectedResponseError("Root-Me redirect limit exceeded.")

    def download(self, url: str) -> bytes:
        """Fetch a public HTTPS resource without any account cookies, across redirects."""
        for _ in range(6):
            parts = urlsplit(url)
            if parts.scheme != "https" or parts.username or parts.password:
                raise ValueError("Resource downloads require HTTPS without user-info.")
            if self.browser and parts.hostname == WEB_HOST:
                response = self.browser.download(url)
            else:
                response = self._send("GET", url, None, None, cookies=parts.hostname == WEB_HOST)
            if not response.is_redirect:
                check_response(response)
                return response.content
            url = urljoin(str(response.url), response.headers.get("location", ""))
        raise UnexpectedResponseError("Resource redirect limit exceeded.")

    def _require_auth(self, required: bool) -> None:
        """Reject missing credentials before an authenticated operation."""
        if not required:
            return
        if not self.session.spip_session:
            expired = any(c.name == "spip_session" for c in self.session.cookies)
            raise AuthenticationRequiredError(
                "This operation requires account authentication.",
                reason="expired" if expired else "missing",
            )

    def _read_retry(
        self,
        method: str,
        url: str,
        data: Mapping[str, str] | None,
        params: Query | None,
        files: Files | None,
        mutation: bool,
    ) -> httpx.Response:
        """Retry only safe reads and only within the configured waiting budget."""
        attempts = self.read_retries if method == "GET" and not mutation else 0
        attempt = 0
        while True:
            try:
                response = self._send(method, url, data, params, files=files)
            except NetworkError:
                if attempt == attempts:
                    raise
                self.wait(min(0.25 * 2**attempt, self.max_retry_delay))
                attempt += 1
                continue
            delay = retry_after(response.headers.get("retry-after"))
            if response.status_code not in {429, 503} or attempt == attempts:
                return response
            pause = delay if delay is not None else 0.25 * 2**attempt
            if pause > self.max_retry_delay:
                return response
            self.wait(pause)
            attempt += 1

    def _send(
        self,
        method: str,
        url: str,
        data: Mapping[str, str] | None,
        params: Query | None,
        *,
        cookies: bool = True,
        files: Files | None = None,
    ) -> httpx.Response:
        """Send one request after stripping the HTTP client's automatic cookie jar."""
        self.http.cookies.clear()
        parts = urlsplit(url)
        cookie = self.session.cookie_header(parts.hostname or "", parts.path) if cookies else ""
        headers = {"User-Agent": self.session.user_agent, "Cookie": cookie}
        if self.browser and cookies and parts.hostname == WEB_HOST:
            return self.browser.request(
                httpx.Request(method, url, data=data, params=params, files=files)
            )
        try:
            return self.http.request(
                method, url, data=data, params=params, headers=headers, files=files
            )
        except httpx.RequestError:
            raise NetworkError("Root-Me request failed; the outcome may be unknown.") from None

    def _remember(self, response: httpx.Response) -> None:
        """Keep website cookies while never widening their effective host scope."""
        if response.url.host != WEB_HOST:
            return
        cookies = {(c.name, c.path): c for c in self.session.cookies}
        for cookie in response.cookies.jar:
            cookies[cookie.name, cookie.path] = SessionCookie(
                cookie.name,
                cookie.value or "",
                WEB_HOST,
                cookie.path,
                cookie.expires,
            )
        self.session.cookies = tuple(cookies.values())
