import httpx
import pytest

from rootme_sdk import (
    AuthenticationRequiredError,
    HumanInterventionRequiredError,
    NotFoundError,
    PermissionDeniedError,
    RateLimitedError,
    UnexpectedResponseError,
)
from rootme_sdk.responses import check_response, retry_after

WEB = "https://www.root-me.org/"


def response(status: int, text: str = "") -> httpx.Response:
    return httpx.Response(status, text=text, request=httpx.Request("GET", WEB))


def test_retry_after_formats() -> None:
    assert retry_after(None) is None and retry_after("bad") is None
    assert retry_after("5") == 5 and retry_after("-1") == 0
    assert retry_after("Sun, 06 Nov 1994 08:49:37 GMT") == 0
    assert retry_after("Sun, 06 Nov 2094 08:49:37 GMT") > 0


@pytest.mark.parametrize(
    "status,kind",
    [
        (401, AuthenticationRequiredError),
        (403, PermissionDeniedError),
        (404, NotFoundError),
        (429, RateLimitedError),
        (500, UnexpectedResponseError),
    ],
)
def test_response_failures(status: int, kind: type[Exception]) -> None:
    with pytest.raises(kind):
        check_response(response(status))
    check_response(response(200))


@pytest.mark.parametrize("marker", ["anubis_challenge", "anubis_version", "cf-chl-test"])
def test_human_gate_before_http_status(marker: str) -> None:
    with pytest.raises(HumanInterventionRequiredError) as info:
        check_response(response(403, marker))
    assert info.value.url == WEB
