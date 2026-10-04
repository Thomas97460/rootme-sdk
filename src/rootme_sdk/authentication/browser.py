"""Explicit optional Playwright assistance; ordinary API clients never import it."""

from __future__ import annotations

from base64 import b64decode, b64encode
from time import monotonic
from typing import cast

import httpx

from ..errors import (
    AuthenticationRequiredError,
    HumanInterventionRequiredError,
    NetworkError,
    RootMeError,
    UnexpectedResponseError,
)
from ..urls import platform_url
from .session import DEFAULT_AGENT, WEB_HOST, Session, SessionCookie

_FETCH_SCRIPT = """async ({url, method, body, contentType, timeout}) => {
              const bytes = body === null ? undefined
                : Uint8Array.from(atob(body), c => c.charCodeAt(0));
              const r = await fetch(url, {method, body: bytes, credentials: 'include',
                redirect: 'manual',
                signal: AbortSignal.timeout(timeout), headers: {'Content-Type': contentType}});
              const result = new Uint8Array(await r.arrayBuffer());
              let text = ''; for (const value of result) text += String.fromCharCode(value);
              return {status: r.status, body: btoa(text)};
            }"""


class BrowserSession:
    """An explicitly opened browser kept alive for JS-dependent website operations."""

    def __init__(
        self,
        session: Session,
        *,
        executable_path: str | None = None,
        headless: bool = False,
        timeout: float = 180,
    ) -> None:
        """Open an isolated browser without using the user's ordinary browser profile."""
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            raise RootMeError(
                "Install rootme-sdk[browser] and a Playwright Chromium browser."
            ) from None
        self.session, self.timeout = session, timeout
        self.engine = sync_playwright().start()
        try:
            self.browser = self.engine.chromium.launch(
                headless=headless, executable_path=executable_path
            )
            agent = session.user_agent if session.user_agent != DEFAULT_AGENT else None
            self.context = self.browser.new_context(user_agent=agent)
            self._install_cookies()
            self.page = self.context.new_page()
        except Exception:
            self.engine.stop()
            raise

    def _install_cookies(self) -> None:
        """Constrain every imported browser cookie to the website host."""
        self.context.add_cookies(
            [
                {
                    "name": c.name,
                    "value": c.value,
                    "domain": WEB_HOST,
                    "path": c.path,
                    "expires": c.expires if c.expires is not None else -1,
                    "secure": True,
                }
                for c in self.session.cookies
                if c.valid()
            ]
        )

    def close(self) -> None:
        """Release the browser and Playwright process, including on context exit."""
        self.engine.stop()

    def prepare(self) -> Session:
        """Prepare anonymous JS-capable website access without requiring account login."""
        self.request(httpx.Request("GET", "https://www.root-me.org/"))
        return self.session

    def authenticate(self, username: str | None = None, password: str | None = None) -> Session:
        """Authenticate without allowing Playwright call logs to reveal supplied passwords."""
        from playwright.sync_api import Error as PlaywrightError

        try:
            return self._authenticate(username, password)
        except PlaywrightError:
            raise NetworkError("Browser authentication failed; retry explicitly.") from None

    def _authenticate(self, username: str | None = None, password: str | None = None) -> Session:
        """Allow manual login or fill supplied credentials, then capture the web session."""
        self.page.goto("https://www.root-me.org/?page=login&lang=en", wait_until="domcontentloaded")
        self._verification()
        if username is not None and password is not None and not self._authenticated():
            self.page.locator('input[name="var_login"]').fill(username)
            self.page.locator('input[name="password"]').fill(password)
            self.page.locator('#formulaire_login input[type="submit"]').click()
        deadline = monotonic() + self.timeout
        while monotonic() < deadline:
            self._sync()
            if self._authenticated():
                return self.session
            self.page.wait_for_timeout(250)
        raise AuthenticationRequiredError(
            "Browser login did not produce an authenticated session before timeout.",
            reason="rejected" if username is not None else "missing",
        )

    def _authenticated(self) -> bool:
        """Require both a current cookie and the observed authenticated account menu."""
        return (
            bool(self.session.spip_session)
            and self.page.locator('a[href*="action=logout"]').count() > 0
        )

    def _verification(self) -> None:
        """Wait for the site's own JavaScript or human verification to finish."""
        from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

        try:
            self.page.wait_for_function(
                "!document.querySelector('#anubis_challenge, #anubis_version, [id^=cf-chl-]')",
                timeout=self.timeout * 1000,
            )
        except PlaywrightTimeoutError:
            raise HumanInterventionRequiredError("https://www.root-me.org/") from None
        self._sync()

    def _sync(self) -> None:
        """Refresh isolated browser cookies and preserve its actual user agent."""
        self.session.cookies = tuple(
            SessionCookie(
                c["name"],
                c["value"],
                WEB_HOST,
                c["path"],
                c["expires"] if c["expires"] != -1 else None,
            )
            for c in self.context.cookies("https://www.root-me.org/")
        )
        self.session.user_agent = str(self.page.evaluate("navigator.userAgent"))

    def request(self, request: httpx.Request) -> httpx.Response:
        """Navigate for reads; send writes once without automatically following redirects."""
        from playwright.sync_api import Error as PlaywrightError

        platform_url(str(request.url))
        if request.url.host != WEB_HOST:
            raise ValueError("Browser requests are limited to the website.")
        try:
            return self._get(request) if request.method == "GET" else self._fetch(request)
        except PlaywrightError:
            raise NetworkError("Browser request failed; its outcome may be unknown.") from None

    def _get(self, request: httpx.Request) -> httpx.Response:
        """Return the rendered document after native browser verification."""
        response = self.page.goto(str(request.url), wait_until="domcontentloaded")
        self._verification()
        platform_url(self.page.url)
        if response is None:
            raise UnexpectedResponseError("Browser navigation produced no response.")
        return httpx.Response(
            response.status, text=self.page.content(), request=httpx.Request("GET", self.page.url)
        )

    def _fetch(self, request: httpx.Request) -> httpx.Response:
        """Send encoded or multipart bodies with an abort deadline and no write redirects."""
        body = b64encode(request.read()).decode() if request.method != "GET" else None
        data = cast(
            dict[str, str | int],
            self.page.evaluate(
                _FETCH_SCRIPT,
                {
                    "url": str(request.url),
                    "method": request.method,
                    "body": body,
                    "contentType": request.headers.get("content-type", "application/octet-stream"),
                    "timeout": self.timeout * 1000,
                },
            ),
        )
        self._sync()
        if data["status"] == 0:
            raise UnexpectedResponseError("Write redirected; its outcome requires confirmation.")
        return httpx.Response(
            int(data["status"]), content=b64decode(str(data["body"])), request=request
        )

    def download(self, url: str) -> httpx.Response:
        """Read a same-origin binary attachment without converting it into rendered HTML."""
        platform_url(url)
        if httpx.URL(url).host != WEB_HOST:
            raise ValueError("Browser downloads must use the website host.")
        from playwright.sync_api import Error as PlaywrightError

        try:
            return self._fetch(httpx.Request("GET", url))
        except PlaywrightError:
            raise NetworkError("Browser download failed.") from None
