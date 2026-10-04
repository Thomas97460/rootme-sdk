import builtins
from base64 import b64decode, b64encode
from unittest.mock import MagicMock

import httpx
import pytest
from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from rootme_sdk import (
    AuthenticationRequiredError,
    HumanInterventionRequiredError,
    NetworkError,
    RootMeError,
    Session,
    SessionCookie,
    UnexpectedResponseError,
)
from rootme_sdk.authentication.browser import BrowserSession

WEB = "https://www.root-me.org/"


@pytest.fixture
def engine(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    instance = MagicMock()
    monkeypatch.setattr(
        "playwright.sync_api.sync_playwright", lambda: MagicMock(start=lambda: instance)
    )
    context = instance.chromium.launch.return_value.new_context.return_value
    context.cookies.return_value = []
    page = context.new_page.return_value
    page.url = WEB
    page.goto.return_value.status = 200
    page.evaluate.return_value = "Browser/1"
    page.locator.return_value.count.return_value = 1
    return instance


def cookie(value: str = "test-session", expires: int = -1) -> dict[str, object]:
    return {
        "name": "spip_session",
        "value": value,
        "domain": "www.root-me.org",
        "path": "/",
        "expires": expires,
    }


def test_optional_extra_is_required_only_when_opened(monkeypatch: pytest.MonkeyPatch) -> None:
    original = builtins.__import__

    def unavailable(name: str, *args: object, **kwargs: object) -> object:
        if name == "playwright.sync_api":
            raise ImportError
        return original(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", unavailable)
    with pytest.raises(RootMeError, match=r"rootme-sdk\[browser\]"):
        BrowserSession(Session())


def test_imported_cookie_scope_and_startup_cleanup(engine: MagicMock) -> None:
    state = Session(
        cookies=(
            SessionCookie("spip_session", "test-session", expires=10**12),
            SessionCookie("expired", "x", expires=0),
        ),
        user_agent="Browser/1",
    )
    adapter = BrowserSession(state, headless=True)
    cookies = adapter.context.add_cookies.call_args.args[0]
    assert len(cookies) == 1 and cookies[0]["domain"] == "www.root-me.org"
    assert cookies[0]["expires"] == 10**12
    adapter.close()
    engine.stop.assert_called_once()
    engine.chromium.launch.side_effect = PlaywrightError("startup failure")
    with pytest.raises(PlaywrightError):
        BrowserSession(Session())
    assert engine.stop.call_count == 2


def test_authenticated_cookie_capture_and_rendered_page(engine: MagicMock) -> None:
    adapter = BrowserSession(Session())
    adapter.context.cookies.return_value = [cookie(expires=10**12)]
    assert adapter.authenticate().spip_session == "test-session"
    assert adapter.session.user_agent == "Browser/1"
    adapter.page.content.return_value = "<p>Rendered</p>"
    assert adapter.prepare() is adapter.session
    response = adapter.request(httpx.Request("GET", WEB))
    assert response.text == "<p>Rendered</p>" and response.status_code == 200
    adapter.page.goto.return_value = None
    with pytest.raises(UnexpectedResponseError):
        adapter.request(httpx.Request("GET", WEB))
    with pytest.raises(ValueError):
        adapter.request(httpx.Request("GET", "https://api.www.root-me.org/challenges"))
    adapter.close()


def test_browser_password_fill_and_bounded_login_poll(
    engine: MagicMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    adapter = BrowserSession(Session(), timeout=10)
    adapter.context.cookies.side_effect = [[], [], [cookie()]]
    monkeypatch.setattr("rootme_sdk.authentication.browser.monotonic", lambda: 0)
    assert adapter.authenticate("Example", "synthetic-password").spip_session == "test-session"
    fills = [call.args[0] for call in adapter.page.locator.return_value.fill.call_args_list]
    assert fills == ["Example", "synthetic-password"]
    adapter.page.wait_for_timeout.assert_called_once_with(250)
    adapter.close()


def test_cookie_without_account_menu_does_not_skip_password_login(engine: MagicMock) -> None:
    adapter = BrowserSession(Session())
    adapter.context.cookies.side_effect = [[cookie("anonymous")], [cookie()]]
    adapter.page.locator.return_value.count.side_effect = [0, 1]
    assert adapter.authenticate("Example", "synthetic-password").spip_session == "test-session"
    assert adapter.page.locator.return_value.fill.call_count == 2
    adapter.close()


def test_manual_login_timeout_and_human_verification(
    engine: MagicMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    adapter = BrowserSession(Session(), timeout=1)
    times = iter([0, 2])
    monkeypatch.setattr("rootme_sdk.authentication.browser.monotonic", lambda: next(times))
    with pytest.raises(AuthenticationRequiredError):
        adapter.authenticate()
    adapter.page.wait_for_function.side_effect = PlaywrightTimeoutError("timeout")
    with pytest.raises(HumanInterventionRequiredError):
        adapter.authenticate()
    adapter.close()


def test_browser_mutation_encoding_redirection_and_network_errors(engine: MagicMock) -> None:
    adapter = BrowserSession(Session())
    adapter.context.cookies.return_value = [cookie()]
    payload = {"status": 200, "body": b64encode(b"feedback").decode()}
    adapter.page.evaluate.side_effect = [payload, "Browser/1"]
    request = httpx.Request(
        "POST",
        WEB,
        data={"passe": "synthetic-answer"},
        files={"avatar": ("test.txt", b"file", "text/plain")},
    )
    response = adapter.request(request)
    assert response.content == b"feedback"
    args = adapter.page.evaluate.call_args_list[0].args[1]
    assert b"test.txt" in b64decode(args["body"]) and "multipart" in args["contentType"]
    adapter.page.evaluate.side_effect = [{"status": 0, "body": ""}, "Browser/1"]
    with pytest.raises(UnexpectedResponseError):
        adapter.request(httpx.Request("POST", WEB, data={"passe": "synthetic-answer"}))
    adapter.page.goto.side_effect = PlaywrightError("synthetic-secret")
    with pytest.raises(NetworkError) as info:
        adapter.request(httpx.Request("GET", WEB))
    assert "synthetic-secret" not in str(info.value)
    with pytest.raises(NetworkError) as authentication:
        adapter.authenticate("Example", "synthetic-password")
    assert "synthetic-secret" not in str(authentication.value)
    adapter.close()


def test_binary_download(engine: MagicMock) -> None:
    adapter = BrowserSession(Session())
    adapter.page.evaluate.side_effect = [
        {"status": 200, "body": b64encode(b"\x00binary").decode()},
        "Browser/1",
    ]
    assert adapter.download(WEB + "file").content == b"\x00binary"
    adapter.page.evaluate.side_effect = PlaywrightError("synthetic-secret")
    with pytest.raises(NetworkError):
        adapter.download(WEB + "file")
    with pytest.raises(ValueError):
        adapter.download("https://api.www.root-me.org/file")
    adapter.close()
