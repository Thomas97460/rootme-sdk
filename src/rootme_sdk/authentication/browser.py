"""Managed Playwright assistance for Root-Me's JavaScript-dependent website."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from base64 import b64decode, b64encode
from contextlib import suppress
from pathlib import Path
from typing import TYPE_CHECKING, cast
from urllib.parse import parse_qs, urljoin, urlsplit

import httpx

from ..errors import (
    AuthenticationRequiredError,
    BrowserUnavailableError,
    HumanInterventionRequiredError,
    NetworkError,
    RootMeError,
    UnexpectedResponseError,
)
from ..responses import check_response
from ..urls import platform_url
from .session import DEFAULT_AGENT, WEB_HOST, Session, SessionCookie

if TYPE_CHECKING:
    from playwright.sync_api import Response as BrowserResponse

_FETCH_SCRIPT = """async ({url, method, body, contentType, timeout}) => {
              const bytes = body === null ? undefined
                : Uint8Array.from(atob(body), c => c.charCodeAt(0));
              const r = await fetch(url, {method, body: bytes, credentials: 'include',
                redirect: 'manual',
                signal: AbortSignal.timeout(timeout), headers: {'Content-Type': contentType}});
              const result = new Uint8Array(await r.arrayBuffer());
              let text = ''; for (const value of result) text += String.fromCharCode(value);
              return {status: r.status, body: btoa(text),
                retryAfter: r.headers.get('Retry-After') || ''};
            }"""


class BrowserSession:
    """An isolated managed browser kept alive for JS-dependent website operations."""

    def __init__(
        self,
        session: Session,
        *,
        executable_path: str | None = None,
        timeout: float = 180,
    ) -> None:
        """Open an isolated browser without using the user's ordinary browser profile."""
        from playwright.sync_api import Error as PlaywrightError
        from playwright.sync_api import sync_playwright

        if timeout <= 0:
            raise ValueError("Browser timeout must be positive.")
        _require_display()
        self.session, self.timeout = session, timeout
        try:
            self.engine = sync_playwright().start()
        except PlaywrightError:
            raise BrowserUnavailableError("Could not start the browser runtime.") from None
        try:
            self._start(executable_path)
        except Exception:
            self.engine.stop()
            raise

    def _start(self, executable_path: str | None) -> None:
        """Start only headed Chromium and translate expected browser startup failures."""
        from playwright.sync_api import Error as PlaywrightError

        try:
            executable = _executable(
                self.engine.chromium.executable_path, executable_path, self.timeout
            )
            self.browser = self.engine.chromium.launch(headless=False, executable_path=executable)
            agent = self.session.user_agent if self.session.user_agent != DEFAULT_AGENT else None
            self.context = self.browser.new_context(user_agent=agent)
            self._install_cookies()
            self.page = self.context.new_page()
            self.page.set_default_timeout(self.timeout * 1000)
        except PlaywrightError:
            raise BrowserUnavailableError(
                "Could not start headed Chromium; check the display and system dependencies."
            ) from None

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

    def authenticate(self, username: str, password: str) -> Session:
        """Authenticate without allowing Playwright call logs to reveal supplied passwords."""
        from playwright.sync_api import Error as PlaywrightError

        try:
            return self._authenticate(username, password)
        except PlaywrightError:
            raise NetworkError("Browser authentication failed; retry explicitly.") from None

    def _authenticate(self, username: str, password: str) -> Session:
        """Await the native login response and verify account access independently of UI."""
        check_response(self._get(httpx.Request("GET", f"https://{WEB_HOST}/?page=login&lang=en")))
        self.page.wait_for_load_state("load")
        self._settle_login()
        self.page.locator('#formulaire_login input[name="var_login"]').fill(username)
        self.page.locator('#formulaire_login input[name="password"]').fill(password)
        self._settle_login()
        with self.page.expect_response(_login_response, timeout=self.timeout * 1000) as pending:
            self.page.locator('#formulaire_login input[type="submit"]').click()
        self._complete_login(pending.value)
        self._confirm_login()
        return self.session

    def _complete_login(self, response: BrowserResponse) -> None:
        """Await decoded AJAX responses or native redirects without relying on menu updates."""
        from playwright.sync_api import Error as PlaywrightError

        try:
            content = b"" if 300 <= response.status < 400 else response.body()
        except PlaywrightError:
            content = b""
        check_response(
            httpx.Response(
                response.status,
                headers=_decoded_headers(response),
                content=content,
                request=httpx.Request("POST", response.url),
            )
        )
        if 300 <= response.status < 400:
            target = platform_url(urljoin(response.url, response.all_headers().get("location", "")))
            self.page.wait_for_url(
                target, wait_until="domcontentloaded", timeout=self.timeout * 1000
            )
        else:
            self._await_login_navigation()
        self._settle_login()

    def _await_login_navigation(self) -> None:
        """Wait for JavaScript-driven login redirects away from the login page."""
        from playwright.sync_api import Error as PlaywrightError

        with suppress(PlaywrightError):
            self.page.wait_for_url(
                lambda u: "?page=login" not in u,
                wait_until="domcontentloaded",
                timeout=min(self.timeout * 1000, 15000),
            )

    def _settle_login(self) -> None:
        """Await page initialization and pending identity AJAX before advancing login."""
        self.page.wait_for_function(
            "window.jQuery && jQuery.isReady && jQuery.active === 0 && "
            "(!window.login_info || !login_info.informe_auteur_en_cours)",
            timeout=self.timeout * 1000,
        )

    def _confirm_login(self) -> None:
        """Verify account-only access within the browser tab that completed authentication."""
        from playwright.sync_api import Error as PlaywrightError

        check_response(
            self._get(httpx.Request("GET", f"https://{WEB_HOST}/?page=preferences&lang=en"))
        )
        with suppress(PlaywrightError):
            self.page.wait_for_selector(
                'input[name="formulaire_action"][value="modifier_auteur"]',
                timeout=min(self.timeout * 1000, 5000),
            )
        editable = self.page.locator(
            'input[name="formulaire_action"][value="modifier_auteur"]'
        ).count()
        if not self.session.spip_session or not editable:
            raise AuthenticationRequiredError(
                "Login did not grant account access.", reason="rejected"
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
            response.status,
            headers=_decoded_headers(response),
            text=self.page.content(),
            request=httpx.Request("GET", self.page.url),
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
        headers = {"Retry-After": str(data["retryAfter"])} if data.get("retryAfter") else {}
        return httpx.Response(
            int(data["status"]),
            headers=headers,
            content=b64decode(str(data["body"])),
            request=request,
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


def _decoded_headers(response: BrowserResponse) -> dict[str, str]:
    """Preserve rate-limit headers without decoding browser response bodies a second time."""
    return {
        name: value
        for name, value in response.all_headers().items()
        if name.lower() not in {"content-encoding", "content-length"}
    }


def _require_display() -> None:
    """Reject unsupported Linux environments before starting or downloading a browser."""
    if sys.platform == "linux" and not os.environ.get("DISPLAY"):
        raise BrowserUnavailableError("Headed Chromium requires an X11 display (DISPLAY) on Linux.")


def _login_response(response: BrowserResponse) -> bool:
    """Identify the website's native login POST in the isolated page."""
    return (
        response.request.method == "POST"
        and urlsplit(response.url).hostname == WEB_HOST
        and parse_qs(response.request.post_data or "").get("formulaire_action") == ["login"]
    )


def _executable(default: str, requested: str | None, timeout: float) -> str:
    """Find installed Chromium, or install its Playwright-managed binary on demand."""
    if requested is not None:
        return requested
    installed = _system_chromium()
    if installed:
        return installed
    if not Path(default).is_file():
        try:
            subprocess.run(
                [sys.executable, "-m", "playwright", "install", "chromium", "--no-shell"],
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=timeout,
            )
        except (OSError, subprocess.SubprocessError):
            raise RootMeError("Automatic Chromium setup failed.") from None
        if not Path(default).is_file():
            raise RootMeError("Automatic Chromium setup did not produce a browser.")
    return default


def _system_chromium() -> str | None:
    """Locate common Chrome/Chromium installations without reading browser profiles."""
    for name in ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser", "msedge"):
        if executable := shutil.which(name):
            return executable
    locations = [Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")]
    for variable in ("LOCALAPPDATA", "PROGRAMFILES", "PROGRAMFILES(X86)"):
        if directory := os.environ.get(variable):
            locations.append(Path(directory) / "Google/Chrome/Application/chrome.exe")
    return next((str(path) for path in locations if path.is_file()), None)
