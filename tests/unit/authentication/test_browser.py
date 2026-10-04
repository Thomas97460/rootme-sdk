import subprocess
from base64 import b64decode, b64encode
from pathlib import Path
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
from rootme_sdk.authentication.browser import (
    BrowserSession,
    _executable,
    _headless,
    _system_chromium,
)

WEB = "https://www.root-me.org/"


@pytest.fixture
def engine(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    instance = MagicMock()
    monkeypatch.setattr(
        "rootme_sdk.authentication.browser._executable",
        lambda default, requested, timeout: requested or "synthetic-chromium",
    )
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


def test_invalid_browser_timeout(engine: MagicMock) -> None:
    with pytest.raises(ValueError, match="positive"):
        BrowserSession(Session(), timeout=0)
    engine.chromium.launch.assert_not_called()


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
    adapter.page.wait_for_load_state.assert_called_once_with("load")
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


def test_supplied_credentials_timeout_reports_rejected_authentication(
    engine: MagicMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    adapter = BrowserSession(Session(), timeout=1)
    times = iter([0, 2])
    monkeypatch.setattr("rootme_sdk.authentication.browser.monotonic", lambda: next(times))
    with pytest.raises(AuthenticationRequiredError) as failure:
        adapter.authenticate("Example", "synthetic-password")
    assert failure.value.reason == "rejected"
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


def test_automatic_display_selection(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("rootme_sdk.authentication.browser.sys.platform", "linux")
    monkeypatch.delenv("DISPLAY", raising=False)
    monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)
    assert _headless(None) and _headless(True)
    assert not _headless(False)
    monkeypatch.setenv("DISPLAY", ":synthetic")
    assert not _headless(None)
    monkeypatch.delenv("DISPLAY")
    monkeypatch.setenv("WAYLAND_DISPLAY", "synthetic")
    assert not _headless(None)
    monkeypatch.setattr("rootme_sdk.authentication.browser.sys.platform", "darwin")
    monkeypatch.delenv("WAYLAND_DISPLAY")
    assert not _headless(None)


def test_system_chromium_detection(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr("rootme_sdk.authentication.browser.shutil.which", lambda name: "/chromium")
    assert _system_chromium() == "/chromium"
    monkeypatch.setattr("rootme_sdk.authentication.browser.shutil.which", lambda name: None)
    for variable in ("LOCALAPPDATA", "PROGRAMFILES", "PROGRAMFILES(X86)"):
        monkeypatch.delenv(variable, raising=False)
    monkeypatch.setattr(Path, "is_file", lambda path: str(path).startswith("/Applications/"))
    assert _system_chromium().endswith("Google Chrome")
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setattr(Path, "is_file", lambda path: path.name == "chrome.exe")
    assert _system_chromium() == str(tmp_path / "Google/Chrome/Application/chrome.exe")
    monkeypatch.setattr(Path, "is_file", lambda path: False)
    assert _system_chromium() is None


def test_explicit_system_and_cached_executables(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    install = MagicMock()
    monkeypatch.setattr("rootme_sdk.authentication.browser.subprocess.run", install)
    monkeypatch.setattr("rootme_sdk.authentication.browser._system_chromium", lambda: "/system")
    assert _executable("/missing", "/chosen", 1) == "/chosen"
    assert _executable("/missing", None, 1) == "/system"
    monkeypatch.setattr("rootme_sdk.authentication.browser._system_chromium", lambda: None)
    cached = tmp_path / "chromium"
    cached.touch()
    assert _executable(str(cached), None, 1) == str(cached)
    install.assert_not_called()


def test_missing_browser_is_installed_automatically(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr("rootme_sdk.authentication.browser._system_chromium", lambda: None)
    target = tmp_path / "chromium"
    install = MagicMock(side_effect=lambda *args, **kwargs: target.touch())
    monkeypatch.setattr("rootme_sdk.authentication.browser.subprocess.run", install)
    assert _executable(str(target), None, 10) == str(target)
    assert install.call_args.args[0][1:] == [
        "-m",
        "playwright",
        "install",
        "chromium",
        "--no-shell",
    ]
    assert install.call_args.kwargs["timeout"] == 10


@pytest.mark.parametrize("error", [OSError("private"), subprocess.TimeoutExpired("private", 1)])
def test_browser_installation_failure_is_private(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, error: Exception
) -> None:
    monkeypatch.setattr("rootme_sdk.authentication.browser._system_chromium", lambda: None)
    monkeypatch.setattr(
        "rootme_sdk.authentication.browser.subprocess.run", MagicMock(side_effect=error)
    )
    with pytest.raises(RootMeError) as result:
        _executable(str(tmp_path / "missing"), None, 1)
    assert "private" not in str(result.value)


def test_incomplete_browser_download_is_rejected(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr("rootme_sdk.authentication.browser._system_chromium", lambda: None)
    monkeypatch.setattr("rootme_sdk.authentication.browser.subprocess.run", MagicMock())
    with pytest.raises(RootMeError, match="did not produce"):
        _executable(str(tmp_path / "missing"), None, 1)
