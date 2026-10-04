from pathlib import Path
from unittest.mock import MagicMock
from urllib.parse import parse_qs

import httpx
import pytest

from rootme_sdk import (
    AuthenticationRequiredError,
    Resource,
    RootMeClient,
    Session,
    SubmissionStatus,
    UnexpectedResponseError,
    Upload,
)
from rootme_sdk.client import _find_form, _password
from rootme_sdk.parsers.web import page

WEB = "https://www.root-me.org/"
API = "https://api.www.root-me.org"
CHALLENGE = WEB + "en/Challenges/Example/Test"


def test_already_solved_feedback_does_not_send_another_answer() -> None:
    handler = MagicMock(
        return_value=httpx.Response(
            200,
            text=(
                '<div id="formulaire_validation_challenge"><p class="reponse_formulaire_ok">'
                "You have already validated this challenge.</p></div>"
            ),
        )
    )
    with RootMeClient(
        spip_session="test-session", transport=httpx.MockTransport(handler)
    ) as client:
        assert (
            client.submit_answer(CHALLENGE, "synthetic-answer").status
            == SubmissionStatus.ALREADY_SOLVED
        )
    assert handler.call_count == 1


def test_official_api_methods_and_documented_filters() -> None:
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        path = request.url.path
        if path.startswith("/challenges"):
            data = {"titre": "Example", "score": "10", "url_challenge": CHALLENGE}
        else:
            assert path == "/auteurs/2"
            data = {"nom": "Example", "id_auteur": "2", "score": "10", "position": "4"}
        return httpx.Response(200, json=[data, {"rel": "self", "href": str(request.url)}])

    with RootMeClient(
        spip_session="test-session", transport=httpx.MockTransport(handler)
    ) as client:
        assert client.get_challenge(7).id == 7
        assert (
            client.list_challenges(
                title="Test", subtitle="Subtitle", language="en", score=10, author_ids=[1, 2]
            )
            .items[0]
            .score
            == 10
        )
        assert calls[-1].url.params.get_list("id_auteur[]") == ["1", "2"]
        assert calls[-1].url.params["titre"] == "Test"
        assert client.get_user(2).position == 4
    assert all(r.headers["cookie"] == "spip_session=test-session" for r in calls)


def test_lazy_pagination_and_metadata() -> None:
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if request.url.params.get("page") == "2":
            return httpx.Response(200, json={"1": {"titre": "Second"}})
        return httpx.Response(
            200,
            json=[{"0": {"titre": "First"}}, {"rel": "next", "href": API + "/challenges?page=2"}],
        )

    with RootMeClient(
        spip_session="test-session", transport=httpx.MockTransport(handler)
    ) as client:
        iterator = client.iter_challenges(titre="Test")
        assert calls == []
        assert next(iterator).title == "First"
        assert len(calls) == 1
        assert next(iterator).title == "Second"
        assert len(calls) == 2 and "titre" not in calls[-1].url.params
        with pytest.raises(StopIteration):
            next(iterator)


@pytest.mark.parametrize(
    "target,kind",
    [
        (API + "/challenges", UnexpectedResponseError),
        (WEB, UnexpectedResponseError),
        ("https://evil.example/challenges", ValueError),
    ],
)
def test_pagination_cycles_and_host_confinement(target: str, kind: type[Exception]) -> None:
    handler = MagicMock(
        return_value=httpx.Response(
            200, json=[{"titre": "Example"}, {"rel": "next", "href": target}]
        )
    )
    with RootMeClient(
        spip_session="test-session", transport=httpx.MockTransport(handler)
    ) as client:
        iterator = client.iter_challenges()
        assert next(iterator).title == "Example"
        with pytest.raises(kind):
            next(iterator)
        assert handler.call_count == 1


def test_boundary_validation_and_missing_api_details() -> None:
    with pytest.raises(ValueError):
        RootMeClient(session=Session(), spip_session="test-session")
    handler = MagicMock(return_value=httpx.Response(200, json=[]))
    with RootMeClient(
        spip_session="test-session", transport=httpx.MockTransport(handler)
    ) as client:
        for operation in (
            lambda: client.get_challenge(0),
            lambda: client.get_user(True),
            lambda: client.list_challenges(author_ids=[0]),
            lambda: client.list_categories(language="../"),
        ):
            with pytest.raises(ValueError):
                operation()
        with pytest.raises(UnexpectedResponseError):
            client.get_challenge(7)
        with pytest.raises(ValueError):
            client._get_page(API + "/challenges")
        with pytest.raises(ValueError):
            client._get_page(WEB + "?action=logout")
        with pytest.raises(ValueError):
            client.submit_answer(CHALLENGE, "")
    with RootMeClient() as client, pytest.raises(AuthenticationRequiredError):
        client.preferences()
    with (
        RootMeClient(
            spip_session="test-session",
            transport=httpx.MockTransport(lambda r: httpx.Response(200, json={"titre": "No URL"})),
        ) as client,
        pytest.raises(UnexpectedResponseError),
    ):
        client.read_challenge(7)


def test_web_read_categories_and_download(fixture_html: Path, tmp_path: Path) -> None:
    html = (fixture_html / "challenge.html").read_text()
    catalogue = (
        '<a href="/en/Challenges/Example/">Example</a><a href="/en/Challenges/E'
        'xample/Test">Challenge</a><a href="/en/Challenges/">Index</a><a href="'
        'https://evil.example/en/Challenges/Other/">Other</a>'
    )

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "api.www.root-me.org":
            return httpx.Response(200, json={"titre": "Example", "url_challenge": CHALLENGE})
        if request.url.path.endswith("/Challenges/"):
            return httpx.Response(200, text=catalogue)
        if request.url.path.endswith("file"):
            assert request.headers["cookie"] == ""
            return httpx.Response(200, content=b"file")
        return httpx.Response(200, text=html)

    with RootMeClient(
        spip_session="test-session", transport=httpx.MockTransport(handler)
    ) as client:
        assert client.get_challenge(CHALLENGE).id == 7
        assert client.read_challenge(7).id == 7
        assert [c.title for c in client.list_categories()] == ["Example"]
        assert client.download("https://repository.root-me.org/file") == b"file"
        target = tmp_path / "file"
        assert client.download(Resource("https://repository.root-me.org/file"), target) == b"file"
        assert target.read_bytes() == b"file"


def test_login_file_and_transient_tokens(fixture_html: Path, tmp_path: Path) -> None:
    calls: list[httpx.Request] = []
    login = (fixture_html / "login.html").read_text()

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if request.method == "GET":
            return httpx.Response(200, text=login.replace("synthetic-token", f"token-{len(calls)}"))
        fields = parse_qs(request.content.decode())
        assert fields["formulaire_action_args"] == ["token-2"]
        assert fields["password"] == ["synthetic-password"] and fields["var_login"] == ["Example"]
        return httpx.Response(
            200,
            text='<a href="/?action=logout">Logout</a>',
            headers={"set-cookie": "spip_session=test-session; Path=/"},
        )

    secret = tmp_path / "password"
    secret.write_text("synthetic-password\n")
    with RootMeClient(transport=httpx.MockTransport(handler)) as client:
        assert client.login("Example", password_file=secret).spip_session == "test-session"
        assert not hasattr(client.session, "password")
        assert [c.method for c in calls] == ["GET", "GET", "POST"]


def test_bad_login_and_password_sources(fixture_html: Path, tmp_path: Path) -> None:
    login = (fixture_html / "login.html").read_text()
    with (
        RootMeClient(
            transport=httpx.MockTransport(lambda r: httpx.Response(200, text=login))
        ) as client,
        pytest.raises(AuthenticationRequiredError),
    ):
        client.login("Example", "synthetic-password")
    for username, password, path in [
        ("", "x", None),
        ("Example", None, None),
        ("Example", "x", tmp_path / "unused"),
        ("Example", "", None),
    ]:
        with pytest.raises(ValueError):
            _password(username, password, path)
    secret = tmp_path / "password"
    secret.write_text("")
    with pytest.raises(ValueError):
        _password("Example", None, secret)


def test_cookie_without_account_access_is_rejected(fixture_html: Path) -> None:
    login = (fixture_html / "login.html").read_text()

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, text=login, headers={"set-cookie": "spip_session=anonymous; Path=/"}
        )

    with RootMeClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(AuthenticationRequiredError) as failure:
            client.login("Example", "synthetic-password")
        assert failure.value.reason == "rejected"
        with pytest.raises(AuthenticationRequiredError) as failure:
            client.preferences()
        assert failure.value.reason == "rejected"


def test_explicit_browser_login_and_cleanup(monkeypatch: pytest.MonkeyPatch) -> None:
    browser = MagicMock()
    factory = MagicMock(return_value=browser)
    monkeypatch.setattr("rootme_sdk.authentication.browser.BrowserSession", factory)
    state = Session()
    browser.authenticate.return_value = state
    browser.prepare.return_value = state
    with RootMeClient(session=state) as client:
        assert client.login("Example", "synthetic-password", browser=True) == state
        assert client.open_browser() == state
        assert browser.close.call_count == 1
        assert client.open_browser(authenticate=False) == state
        assert browser.close.call_count == 2
    assert browser.close.call_count == 3
    browser.authenticate.side_effect = AuthenticationRequiredError("failed")
    with RootMeClient() as client, pytest.raises(AuthenticationRequiredError):
        client.open_browser()
    assert browser.close.call_count == 4


def test_logout_clears_state_even_on_failure() -> None:
    state = Session()
    with RootMeClient(session=state) as client:
        client.logout()
        assert state.cookies == ()
    state = Session(cookies=())
    from rootme_sdk import SessionCookie

    state.cookies = (SessionCookie("spip_session", "test-session"),)
    with RootMeClient(
        session=state, transport=httpx.MockTransport(lambda r: httpx.Response(500))
    ) as client:
        browser = MagicMock()
        browser.request.return_value = httpx.Response(500, request=httpx.Request("GET", WEB))
        client._transport.browser = browser
        with pytest.raises(UnexpectedResponseError):
            client.logout()
        assert state.cookies == () and client._transport.browser is None
        browser.close.assert_called_once()


def test_preferences_upload(fixture_html: Path) -> None:
    html = (fixture_html / "preferences.html").read_text()
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if request.method == "POST":
            assert b"synthetic-token" in request.content and b"avatar.txt" in request.content
            assert b"supprimer_compte" not in request.content
        return httpx.Response(200, text=html)

    with RootMeClient(
        spip_session="test-session", transport=httpx.MockTransport(handler)
    ) as client:
        assert client.preferences().forms[0].name == "modifier_auteur"
        client.update_preferences(
            {"nom": "New"}, files={"avatar": Upload("avatar.txt", b"synthetic-file")}
        )
        form = client.preferences().forms[0]
        with pytest.raises(ValueError):
            client._submit_form(form, {}, files={"unknown": Upload("test", b"x")})
    assert sum(c.method == "POST" for c in calls) == 1


def test_get_form_and_missing_or_ambiguous_form() -> None:
    html = '<form id="search" action="/search"><input name="q"></form>'
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, text=html)

    with RootMeClient(
        spip_session="test-session", transport=httpx.MockTransport(handler)
    ) as client:
        form = client._get_page(WEB).forms[0]
        client._submit_form(form, {"q": "Test"})
        assert calls[-1].url.params["q"] == "Test"
    with pytest.raises(UnexpectedResponseError):
        _find_form(page(html, WEB), "other")
    with pytest.raises(UnexpectedResponseError):
        _find_form(page(html + html, WEB), "search")
    login = '<form><input name="formulaire_action" type="hidden" value="login"></form>'
    with pytest.raises(AuthenticationRequiredError):
        _find_form(page(login, WEB), "search")


@pytest.mark.parametrize(
    "outcome,status",
    [
        ("accepted", SubmissionStatus.ACCEPTED),
        ("rejected", SubmissionStatus.REJECTED),
        ("timeout", SubmissionStatus.INDETERMINATE),
        ("bad-response", SubmissionStatus.INDETERMINATE),
        ("rate-limit", SubmissionStatus.BLOCKED),
    ],
)
def test_submit_once_and_actual_outcome(
    fixture_html: Path, outcome: str, status: SubmissionStatus
) -> None:
    html = (fixture_html / "challenge.html").read_text()
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if request.method == "GET":
            return httpx.Response(200, text=html)
        if outcome == "timeout":
            raise httpx.ReadTimeout("unknown outcome", request=request)
        if outcome == "bad-response":
            return httpx.Response(502)
        if outcome == "rate-limit":
            return httpx.Response(429, headers={"retry-after": "60"})
        css = "reponse_formulaire_ok" if outcome == "accepted" else "reponse_formulaire_erreur"
        return httpx.Response(
            200,
            text=f'<div id="formulaire_validation_challenge"><p class="{css}">'
            "Feedback synthetic-answer</p></div>",
        )

    with RootMeClient(
        spip_session="test-session", transport=httpx.MockTransport(handler)
    ) as client:
        result = client.submit_answer(CHALLENGE, "synthetic-answer")
        assert result.status == status and "synthetic-answer" not in result.message
        if outcome == "rate-limit":
            assert result.retry_after == 60
    assert sum(c.method == "POST" for c in calls) == 1
