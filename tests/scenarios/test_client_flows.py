from pathlib import Path

import httpx
import pytest

from rootme_sdk import AuthenticationRequiredError, RootMeClient, SubmissionStatus

WEB = "https://www.root-me.org/"
CHALLENGE = WEB + "en/Challenges/Example/Test"


def test_password_login_read_download_submit_and_logout(fixture_html: Path) -> None:
    calls: list[httpx.Request] = []
    login = (fixture_html / "login.html").read_text()
    challenge = (fixture_html / "challenge.html").read_text()

    def server(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if request.url.params.get("action") == "logout":
            return httpx.Response(200, text="Logged out")
        if request.url.params.get("page") == "login":
            if request.method == "GET":
                return httpx.Response(200, text=login)
            return httpx.Response(
                200,
                text='<a href="/?action=logout">Logout</a>',
                headers={"set-cookie": "spip_session=test-session; Path=/"},
            )
        if request.url.host == "api.www.root-me.org":
            assert request.headers["cookie"] == "spip_session=test-session"
            return httpx.Response(200, json=[{"titre": "Example", "url_challenge": CHALLENGE}])
        if request.url.path == "/files/example.zip":
            return httpx.Response(302, headers={"location": "https://challenge01.root-me.org/file"})
        if request.url.host == "challenge01.root-me.org":
            assert request.headers["cookie"] == ""
            return httpx.Response(200, content=b"synthetic-archive")
        if request.method == "POST":
            return httpx.Response(200, text='<p class="reponse_formulaire_ok">Validated</p>')
        return httpx.Response(200, text=challenge)

    with RootMeClient(transport=httpx.MockTransport(server)) as client:
        client.login("Example", "synthetic-password")
        result = client.read_challenge(7)
        assert "Read the supplied file" in result.statement
        assert client.download(result.resources[0]) == b"synthetic-archive"
        assert (
            client.submit_answer(CHALLENGE, "synthetic-answer").status == SubmissionStatus.ACCEPTED
        )
        client.logout()
        assert client.session.spip_session is None
    assert sum(request.method == "POST" for request in calls) == 2


def test_api_key_reads_without_browser_and_write_requires_web_session(fixture_html: Path) -> None:
    calls: list[httpx.Request] = []
    challenge = (fixture_html / "challenge.html").read_text()

    def server(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if request.url.host == "api.www.root-me.org":
            assert request.headers["cookie"] == "api_key=test-api"
            return httpx.Response(200, json={"titre": "Example", "score": "10"})
        assert request.headers["cookie"] == ""
        return httpx.Response(200, text=challenge)

    with RootMeClient(api_key="test-api", transport=httpx.MockTransport(server)) as client:
        assert client.get_challenge(7).score == 10
        with pytest.raises(AuthenticationRequiredError):
            client.submit_answer(CHALLENGE, "synthetic-answer")
    assert all(request.method == "GET" for request in calls)
