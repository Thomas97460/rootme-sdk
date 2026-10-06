from unittest.mock import MagicMock

import httpx
import pytest

from rootme_sdk import (
    AuthenticationRequiredError,
    NetworkError,
    RateLimitedError,
    Session,
    SessionCookie,
    UnexpectedResponseError,
)
from rootme_sdk.transport import Transport

WEB = "https://www.root-me.org/"
API = "https://api.www.root-me.org/challenges"


@pytest.mark.parametrize("kwargs", [{"timeout": 0}, {"read_retries": -1}, {"max_retry_delay": -1}])
def test_bad_request_configuration(kwargs: dict[str, int]) -> None:
    with pytest.raises(ValueError):
        Transport(Session(), **kwargs)


def test_missing_authentication_fails_without_request() -> None:
    handler = MagicMock()
    boundary = Transport(Session(), transport=httpx.MockTransport(handler))
    with pytest.raises(AuthenticationRequiredError):
        boundary.request("GET", API, authenticated=True)
    handler.assert_not_called()
    boundary.close()


def test_local_expiry_is_distinct_from_missing_credentials() -> None:
    state = Session(cookies=(SessionCookie("spip_session", "expired", expires=0),))
    boundary = Transport(state)
    with pytest.raises(AuthenticationRequiredError) as info:
        boundary.request("GET", API, authenticated=True)
    assert info.value.reason == "expired"
    boundary.close()


def test_cookie_scope_response_cookie_and_redirects() -> None:
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if request.url.path == "/":
            return httpx.Response(
                302,
                headers={
                    "location": "/next",
                    "set-cookie": "spip_session=renewed; Path=/; Domain=.root-me.org",
                },
            )
        return httpx.Response(200, text="done")

    state = Session(cookies=(SessionCookie("spip_session", "test-session"),))
    boundary = Transport(state, transport=httpx.MockTransport(handler))
    assert boundary.request("GET", WEB).text == "done"
    assert calls[0].headers["cookie"] == "spip_session=test-session"
    assert calls[1].headers["cookie"] == "spip_session=renewed"
    boundary.request("GET", API, authenticated=True)
    assert calls[-1].headers["cookie"] == "spip_session=renewed"
    boundary.close()


def test_mutation_redirects_and_host_rejection() -> None:
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.method)
        return (
            httpx.Response(303, headers={"location": "/done"})
            if request.method == "POST"
            else httpx.Response(200)
        )

    boundary = Transport(Session(), transport=httpx.MockTransport(handler))
    boundary.request("POST", WEB, data={"password": "synthetic"}, mutation=True)
    assert seen == ["POST", "GET"]
    for status, target, kind in [
        (307, "/done", UnexpectedResponseError),
        (302, "https://evil.example/", ValueError),
    ]:
        other = Transport(
            Session(),
            transport=httpx.MockTransport(
                lambda request, status=status, target=target: httpx.Response(
                    status, headers={"location": target}
                )
            ),
        )
        with pytest.raises(kind):
            other.request("POST", WEB)
        other.close()
    boundary.close()


def test_redirect_budget() -> None:
    handler = MagicMock(return_value=httpx.Response(302, headers={"location": "/loop"}))
    boundary = Transport(Session(), transport=httpx.MockTransport(handler))
    with pytest.raises(UnexpectedResponseError, match="redirect limit"):
        boundary.request("GET", WEB)
    assert handler.call_count == 6
    boundary.close()


def test_transient_read_retry_and_terminal_failure() -> None:
    calls: list[httpx.Request] = []
    waits: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if len(calls) == 1:
            raise httpx.ReadTimeout("synthetic secret that must not escape", request=request)
        return httpx.Response(200)

    boundary = Transport(Session(), transport=httpx.MockTransport(handler), wait=waits.append)
    boundary.request("GET", WEB)
    assert len(calls) == 2 and waits == [0.25]
    calls.clear()
    with pytest.raises(NetworkError) as info:
        boundary.request("POST", WEB, data={"passe": "synthetic-answer"}, mutation=True)
    assert len(calls) == 1 and "synthetic secret" not in str(info.value)
    calls.clear()
    with pytest.raises(NetworkError):
        boundary.request("GET", WEB, mutation=True)
    assert len(calls) == 1
    boundary.close()


@pytest.mark.parametrize("status,delay", [(429, "1"), (503, None)])
def test_read_status_retry(status: int, delay: str | None) -> None:
    calls: list[httpx.Request] = []
    waits: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        headers = {"retry-after": delay} if delay else {}
        return httpx.Response(status if len(calls) == 1 else 200, headers=headers)

    boundary = Transport(Session(), transport=httpx.MockTransport(handler), wait=waits.append)
    boundary.request("GET", WEB)
    assert len(calls) == 2 and waits == [1 if delay else 0.25]
    boundary.close()


def test_do_not_wait_beyond_server_budget() -> None:
    handler = MagicMock(return_value=httpx.Response(429, headers={"retry-after": "60"}))
    wait = MagicMock()
    boundary = Transport(Session(), transport=httpx.MockTransport(handler), wait=wait)
    with pytest.raises(RateLimitedError) as info:
        boundary.request("GET", WEB)
    assert info.value.retry_after == 60 and handler.call_count == 1
    wait.assert_not_called()
    boundary.close()


def test_download_redirect_cookie_isolation_and_bad_target() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.url.host == "www.root-me.org":
            return httpx.Response(
                302,
                headers={
                    "location": "https://challenge01.root-me.org/file",
                    "set-cookie": "spip_session=wide; Domain=.root-me.org; Path=/",
                },
            )
        return httpx.Response(200, content=b"\x00file")

    boundary = Transport(
        Session(cookies=(SessionCookie("spip_session", "test-session"),)),
        transport=httpx.MockTransport(handler),
    )
    assert boundary.download(WEB + "file") == b"\x00file"
    assert seen[0].headers["cookie"] == "spip_session=test-session"
    assert seen[1].headers["cookie"] == ""
    for url in ("http://example.org/file", "https://u:p@example.org/file"):
        with pytest.raises(ValueError):
            boundary.download(url)
    boundary.close()


def test_download_redirect_limit_and_browser_transport() -> None:
    boundary = Transport(
        Session(),
        transport=httpx.MockTransport(
            lambda request: httpx.Response(302, headers={"location": WEB})
        ),
    )
    with pytest.raises(UnexpectedResponseError, match="Resource redirect limit"):
        boundary.download(WEB)
    browser = MagicMock()
    browser.request.return_value = httpx.Response(
        200, text="rendered", request=httpx.Request("GET", WEB)
    )
    browser.download.return_value = httpx.Response(
        200, text="file", request=httpx.Request("GET", WEB)
    )
    boundary.browser = browser
    assert boundary.request("GET", WEB).text == "rendered"
    assert boundary.download(WEB) == b"file"
    boundary.close()
    browser.close.assert_called_once()


def test_download_url_sanitization_and_redirect_spaces() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.url.path == "/initial":
            return httpx.Response(
                302,
                headers={"location": "https://repository.root-me.org/file with spaces.pdf"},
            )
        return httpx.Response(200, content=b"content")

    boundary = Transport(Session(), transport=httpx.MockTransport(handler))
    content = boundary.download("https://repository.root-me.org/initial")
    assert content == b"content"
    assert seen[0].url.path == "/initial"
    assert str(seen[1].url) == "https://repository.root-me.org/file%20with%20spaces.pdf"

    content_direct = boundary.download("https://repository.root-me.org/direct spaces.pdf")
    assert content_direct == b"content"
    assert str(seen[2].url) == "https://repository.root-me.org/direct%20spaces.pdf"
    boundary.close()
