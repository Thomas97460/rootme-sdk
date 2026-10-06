import json
from base64 import b64decode, b64encode
from pathlib import Path
from unittest.mock import MagicMock
from urllib.parse import parse_qs

import httpx
import pytest

from rootme_sdk import AuthenticationRequiredError, RootMeClient, SubmissionStatus

WEB = "https://www.root-me.org/"
CHALLENGE = WEB + "en/Challenges/Example/Test"


def test_reusable_session_read_download_submit_and_logout(fixture_html: Path) -> None:
    calls: list[httpx.Request] = []
    challenge = (fixture_html / "challenge.html").read_text(encoding="utf-8")

    def server(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if request.url.params.get("action") == "logout":
            return httpx.Response(200, text="Logged out")
        if request.url.host == "api.www.root-me.org":
            assert request.headers["cookie"] == "spip_session=test-session"
            return httpx.Response(200, json=[{"titre": "Example", "url_challenge": CHALLENGE}])
        if request.url.path == "/files/example.zip":
            return httpx.Response(302, headers={"location": "https://challenge01.root-me.org/file"})
        if request.url.host == "challenge01.root-me.org":
            assert request.headers["cookie"] == ""
            return httpx.Response(200, content=b"synthetic-archive")
        if request.method == "POST":
            return httpx.Response(
                200,
                text='<div id="formulaire_validation_challenge">'
                '<p class="reponse_formulaire_ok">Validated</p></div>',
            )
        return httpx.Response(200, text=challenge)

    with RootMeClient(spip_session="test-session", transport=httpx.MockTransport(server)) as client:
        result = client.read_challenge(7)
        assert "Read the supplied file" in result.statement
        assert client.download(result.resources[0]) == b"synthetic-archive"
        assert (
            client.submit_answer(CHALLENGE, "synthetic-answer").status == SubmissionStatus.ACCEPTED
        )
        client.logout()
        assert client.session.spip_session is None
    assert sum(request.method == "POST" for request in calls) == 1


def test_anonymous_challenge_read_requires_login_for_submission(fixture_html: Path) -> None:
    calls: list[httpx.Request] = []
    challenge = (fixture_html / "challenge.html").read_text(encoding="utf-8")

    def server(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        assert request.headers["cookie"] == ""
        return httpx.Response(200, text=challenge)

    with RootMeClient(transport=httpx.MockTransport(server)) as client:
        assert client.read_challenge(CHALLENGE).score == 10
        with pytest.raises(AuthenticationRequiredError):
            client.submit_answer(CHALLENGE, "synthetic-answer")
    assert all(request.method == "GET" for request in calls)


def test_file_credentials_handle_js_read_and_submit_without_extra_calls(
    fixture_html: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DISPLAY", ":synthetic")
    engine = MagicMock()
    monkeypatch.setattr(
        "playwright.sync_api.sync_playwright", lambda: MagicMock(start=lambda: engine)
    )
    monkeypatch.setattr("rootme_sdk.authentication.browser._executable", lambda *args: "/synthetic")
    context = engine.chromium.launch.return_value.new_context.return_value
    browser_page = context.new_page.return_value
    reply = browser_page.expect_response.return_value.__enter__.return_value.value
    reply.status = 200
    reply.url = WEB + "?page=login"
    reply.body.return_value = b"Synthetic login reply"
    reply.all_headers.return_value = {}
    logged_in = False
    writes = []

    def cookies(*args: object) -> list[dict[str, object]]:
        return (
            [{"name": "spip_session", "value": "synthetic-session", "path": "/", "expires": -1}]
            if logged_in
            else []
        )

    def clicked(**kwargs: object) -> None:
        nonlocal logged_in
        logged_in = True

    def navigate(url: str, **kwargs: object) -> MagicMock:
        browser_page.url = url
        browser_page.content.return_value = (
            fixture_html / ("preferences.html" if "page=preferences" in url else "challenge.html")
        ).read_text(encoding="utf-8")
        return MagicMock(status=200)

    def evaluate(script: str, args: dict[str, object] | None = None) -> object:
        if args is None:
            return "SyntheticBrowser/1"
        fields = parse_qs(b64decode(args["body"]).decode())
        writes.append(fields)
        assert fields["passe"] == ["synthetic-answer"]
        assert fields["formulaire_action_args"] == ["synthetic-token"]
        feedback = (
            '<div id="formulaire_validation_challenge"><p class="success">Validated</p></div>'
        )
        return {"status": 200, "body": b64encode(feedback.encode()).decode()}

    context.cookies.side_effect = cookies
    browser_page.goto.side_effect = navigate
    browser_page.evaluate.side_effect = evaluate
    browser_page.locator.return_value.count.side_effect = lambda: int(logged_in)
    browser_page.locator.return_value.click.side_effect = clicked

    def server(request: httpx.Request) -> httpx.Response:
        if request.url.host == "api.www.root-me.org":
            assert request.headers["cookie"] == "spip_session=synthetic-session"
            return httpx.Response(
                200, json=[{"id_challenge": 7, "titre": "Example", "url_challenge": CHALLENGE}]
            )
        return httpx.Response(200, text='<div id="anubis_challenge"></div>')

    source = tmp_path / "credentials.json"
    source.write_text(json.dumps({"login": "Example", "password": "synthetic-password"}))
    with RootMeClient(credentials_file=source, transport=httpx.MockTransport(server)) as client:
        assert "Read the supplied file" in client.read_challenge(7).statement
        assert client.submit_answer(7, "synthetic-answer").status == SubmissionStatus.ACCEPTED
    assert len(writes) == 1
    assert [call.args[0] for call in browser_page.locator.return_value.fill.call_args_list] == [
        "Example",
        "synthetic-password",
    ]
    engine.stop.assert_called_once()
