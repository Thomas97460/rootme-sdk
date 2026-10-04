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
    BrowserUnavailableError,
    HumanInterventionRequiredError,
    NetworkError,
    RateLimitedError,
    RootMeError,
    Session,
    SessionCookie,
    UnexpectedResponseError,
)
from rootme_sdk.authentication.browser import (
    BrowserSession,
    _executable,
    _login_response,
    _require_display,
    _system_chromium,
)

WEB = "https://www.root-me.org/"


@pytest.fixture
def engine(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    monkeypatch.setenv("DISPLAY", ":synthetic")
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
    page.content.return_value = '<input name="formulaire_action" value="modifier_auteur">'
    reply = page.expect_response.return_value.__enter__.return_value.value
    reply.status = 200
    reply.url = WEB + "?page=login"
    reply.body.return_value = b"Login response"
    reply.all_headers.return_value = {}
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
    adapter = BrowserSession(state)
    cookies = adapter.context.add_cookies.call_args.args[0]
    assert len(cookies) == 1 and cookies[0]["domain"] == "www.root-me.org"
    assert cookies[0]["expires"] == 10**12
    adapter.close()
    engine.stop.assert_called_once()
    engine.chromium.launch.side_effect = PlaywrightError("startup failure")
    with pytest.raises(BrowserUnavailableError):
        BrowserSession(Session())
    assert engine.stop.call_count == 2


def test_authenticated_cookie_capture_and_rendered_page(engine: MagicMock) -> None:
    adapter = BrowserSession(Session())
    adapter.context.cookies.return_value = [cookie(expires=10**12)]
    assert adapter.authenticate("Example", "synthetic-password").spip_session == "test-session"
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


def test_native_login_waits_for_post_and_confirms_account_access(engine: MagicMock) -> None:
    adapter = BrowserSession(Session(), timeout=10)
    adapter.context.cookies.side_effect = [[], [cookie()]]
    login_page = adapter.page
    assert adapter.authenticate("Example", "synthetic-password").spip_session == "test-session"
    assert [call.args[0] for call in login_page.locator.return_value.fill.call_args_list] == [
        "Example",
        "synthetic-password",
    ]
    pending = login_page.expect_response.return_value.__enter__.return_value.value
    login_page.wait_for_load_state.assert_called_once_with("load")
    pending.body.assert_called_once()
    login_page.locator.return_value.click.assert_called_once()
    login_page.wait_for_url.assert_not_called()
    login_page.close.assert_not_called()
    assert adapter.context.new_page.call_count == 1
    assert login_page.goto.call_args_list[-1].args[0] == WEB + "?page=preferences&lang=en"
    engine.chromium.launch.assert_called_once_with(
        headless=False, executable_path="synthetic-chromium"
    )
    adapter.close()


def test_cookie_without_account_access_is_rejected(engine: MagicMock) -> None:
    adapter = BrowserSession(Session())
    adapter.context.cookies.return_value = [cookie("anonymous")]
    adapter.page.locator.return_value.count.return_value = 0
    with pytest.raises(AuthenticationRequiredError) as failure:
        adapter.authenticate("Example", "synthetic-password")
    assert failure.value.reason == "rejected"
    assert adapter.page.locator.return_value.fill.call_count == 2
    adapter.close()


def test_ajax_login_succeeds_when_the_old_account_menu_never_updates(engine: MagicMock) -> None:
    adapter = BrowserSession(Session())
    login_page = adapter.page
    account_form = MagicMock()
    account_form.count.return_value = 1
    stale_menu = MagicMock()
    stale_menu.count.return_value = 0
    login_page.locator.side_effect = lambda selector: (
        account_form if "modifier_auteur" in selector else stale_menu
    )
    adapter.context.cookies.side_effect = [[], [cookie()]]
    assert adapter.authenticate("Example", "synthetic-password").spip_session == "test-session"
    login_page.wait_for_url.assert_not_called()
    assert adapter.page is login_page
    assert adapter.context.new_page.call_count == 1
    login_page.close.assert_not_called()
    adapter.close()


def test_identity_lookup_settles_before_submission_and_account_navigation(
    engine: MagicMock,
) -> None:
    adapter = BrowserSession(Session())
    adapter.context.cookies.return_value = [cookie()]
    page = adapter.page
    events = []

    def wait(script: str, **kwargs: object) -> None:
        if "jQuery.active" in script:
            events.append("ajax-idle")

    page.wait_for_function.side_effect = wait
    page.locator.return_value.fill.side_effect = lambda value: events.append("fill")
    page.locator.return_value.click.side_effect = lambda: events.append("submit")
    reply = page.expect_response.return_value.__enter__.return_value.value
    reply.body.side_effect = lambda: events.append("response-complete") or b"Login response"
    assert adapter.authenticate("Example", "synthetic-password").spip_session == "test-session"
    assert events == [
        "ajax-idle",
        "fill",
        "fill",
        "ajax-idle",
        "submit",
        "response-complete",
        "ajax-idle",
    ]
    adapter.close()


def test_account_form_without_cookie_is_rejected(engine: MagicMock) -> None:
    adapter = BrowserSession(Session())
    with pytest.raises(AuthenticationRequiredError):
        adapter.authenticate("Example", "synthetic-password")
    adapter.close()


def test_browser_verification_timeout(engine: MagicMock) -> None:
    adapter = BrowserSession(Session(), timeout=1)
    adapter.page.wait_for_function.side_effect = PlaywrightTimeoutError("private")
    with pytest.raises(HumanInterventionRequiredError):
        adapter.authenticate("Example", "synthetic-password")
    adapter.page.locator.return_value.click.assert_not_called()
    adapter.close()


def test_login_redirect_confirms_without_reading_redirect_body(engine: MagicMock) -> None:
    adapter = BrowserSession(Session())
    adapter.context.cookies.return_value = [cookie()]
    reply = adapter.page.expect_response.return_value.__enter__.return_value.value
    reply.status = 302
    reply.all_headers.return_value = {"location": "/?page=preferences"}
    assert adapter.authenticate("Example", "synthetic-password").spip_session
    reply.body.assert_not_called()
    adapter.page.wait_for_url.assert_called_once_with(
        WEB + "?page=preferences", wait_until="domcontentloaded", timeout=180000
    )
    adapter.close()


def test_redirect_finishes_before_navigation_to_the_account_page(engine: MagicMock) -> None:
    adapter = BrowserSession(Session())
    login_page = adapter.page
    reply = login_page.expect_response.return_value.__enter__.return_value.value
    reply.status = 302
    reply.all_headers.return_value = {"location": "/?page=preferences"}
    events = []

    def completed(*args: object, **kwargs: object) -> None:
        login_page.close.assert_not_called()
        events.append("native-completed")
        adapter.context.cookies.return_value = [cookie()]

    def navigate(url: str, **kwargs: object) -> MagicMock:
        if "page=preferences" in url:
            login_page.close.assert_not_called()
            assert events == ["native-completed"]
            events.append("account-checked")
        return MagicMock(status=200)

    login_page.wait_for_url.side_effect = completed
    login_page.goto.side_effect = navigate
    assert adapter.authenticate("Example", "synthetic-password").spip_session == "test-session"
    assert events == ["native-completed", "account-checked"]
    login_page.close.assert_not_called()
    assert adapter.context.new_page.call_count == 1
    adapter.close()


def test_unfinished_native_login_never_opens_confirmation_or_replays(engine: MagicMock) -> None:
    adapter = BrowserSession(Session())
    reply = adapter.page.expect_response.return_value.__enter__.return_value.value
    reply.status = 302
    reply.all_headers.return_value = {"location": "/?page=preferences"}
    adapter.page.wait_for_url.side_effect = PlaywrightTimeoutError("private")
    with pytest.raises(NetworkError):
        adapter.authenticate("Example", "synthetic-password")
    assert adapter.context.new_page.call_count == 1
    adapter.page.locator.return_value.click.assert_called_once()
    adapter.close()


def test_login_rate_limit_is_reported_without_resubmission(engine: MagicMock) -> None:
    adapter = BrowserSession(Session())
    reply = adapter.page.expect_response.return_value.__enter__.return_value.value
    reply.status = 429
    reply.all_headers.return_value = {"retry-after": "60"}
    with pytest.raises(RateLimitedError) as result:
        adapter.authenticate("Example", "synthetic-password")
    assert result.value.retry_after == 60
    adapter.page.locator.return_value.click.assert_called_once()
    assert adapter.context.new_page.call_count == 1
    adapter.close()


def test_browser_decoded_login_body_is_not_decompressed_twice(engine: MagicMock) -> None:
    adapter = BrowserSession(Session())
    adapter.context.cookies.return_value = [cookie()]
    reply = adapter.page.expect_response.return_value.__enter__.return_value.value
    reply.all_headers.return_value = {
        "content-encoding": "gzip",
        "content-length": "123",
        "content-type": "text/html",
    }
    assert adapter.authenticate("Example", "synthetic-password").spip_session == "test-session"
    adapter.close()


def test_ambiguous_login_response_is_not_replayed(engine: MagicMock) -> None:
    adapter = BrowserSession(Session())
    adapter.page.expect_response.return_value.__exit__.side_effect = PlaywrightTimeoutError(
        "synthetic-password"
    )
    with pytest.raises(NetworkError) as failure:
        adapter.authenticate("Example", "synthetic-password")
    assert "synthetic-password" not in str(failure.value)
    adapter.page.locator.return_value.click.assert_called_once()
    adapter.close()


@pytest.mark.parametrize(
    "method,url,data,expected",
    [
        ("POST", WEB, "formulaire_action=login", True),
        ("GET", WEB, "formulaire_action=login", False),
        ("POST", "https://evil.example/", "formulaire_action=login", False),
        ("POST", WEB, "formulaire_action=other", False),
        ("POST", WEB, None, False),
    ],
)
def test_login_reply_matches_only_the_login_form(
    method: str, url: str, data: str | None, expected: bool
) -> None:
    assert (
        _login_response(MagicMock(request=MagicMock(method=method, post_data=data), url=url))
        is expected
    )


def test_runtime_startup_error_is_private(
    engine: MagicMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "playwright.sync_api.sync_playwright",
        lambda: MagicMock(start=MagicMock(side_effect=PlaywrightError("private"))),
    )
    with pytest.raises(BrowserUnavailableError) as failure:
        BrowserSession(Session())
    assert "private" not in str(failure.value)
    engine.chromium.launch.assert_not_called()


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


def test_browser_reads_and_writes_preserve_server_retry_after(engine: MagicMock) -> None:
    adapter = BrowserSession(Session())
    navigation = adapter.page.goto.return_value
    navigation.status = 429
    navigation.all_headers.return_value = {
        "retry-after": "30",
        "content-encoding": "gzip",
        "content-length": "500",
    }
    response = adapter.request(httpx.Request("GET", WEB))
    assert response.status_code == 429 and response.headers["retry-after"] == "30"
    assert "content-encoding" not in response.headers
    adapter.page.evaluate.side_effect = [
        {"status": 429, "body": b64encode(b"Limited").decode(), "retryAfter": "60"},
        "Browser/1",
    ]
    response = adapter.request(httpx.Request("POST", WEB, data={"passe": "synthetic-answer"}))
    assert response.status_code == 429 and response.headers["retry-after"] == "60"
    adapter.close()


def test_display_is_required_before_browser_startup(
    engine: MagicMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("rootme_sdk.authentication.browser.sys.platform", "linux")
    monkeypatch.delenv("DISPLAY")
    monkeypatch.setenv("WAYLAND_DISPLAY", "synthetic")
    with pytest.raises(BrowserUnavailableError, match="DISPLAY"):
        BrowserSession(Session())
    engine.chromium.launch.assert_not_called()
    monkeypatch.setenv("DISPLAY", ":synthetic")
    _require_display()
    monkeypatch.delenv("DISPLAY")
    monkeypatch.setattr("rootme_sdk.authentication.browser.sys.platform", "darwin")
    _require_display()


def test_system_chromium_detection(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr("rootme_sdk.authentication.browser.shutil.which", lambda name: "/chromium")
    assert _system_chromium() == "/chromium"
    monkeypatch.setattr("rootme_sdk.authentication.browser.shutil.which", lambda name: None)
    for variable in ("LOCALAPPDATA", "PROGRAMFILES", "PROGRAMFILES(X86)"):
        monkeypatch.delenv(variable, raising=False)
    monkeypatch.setattr(
        Path, "is_file", lambda path: str(path).startswith(str(Path("/Applications")))
    )
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
