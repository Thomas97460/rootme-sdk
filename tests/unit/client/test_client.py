import json
from pathlib import Path
from unittest.mock import MagicMock

import httpx
import pytest

from rootme_sdk import (
    AuthenticationRequiredError,
    Category,
    Challenge,
    Difficulty,
    HumanInterventionRequiredError,
    NotFoundError,
    Resource,
    RootMeClient,
    Session,
    SessionCookie,
    SubmissionStatus,
    UnexpectedResponseError,
    Upload,
)
from rootme_sdk.client.client import _find_form
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


def test_official_api_methods_and_documented_filters(fixture_html: Path) -> None:
    calls: list[httpx.Request] = []
    challenge_html = (fixture_html / "challenge.html").read_text(encoding="utf-8")

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        path = request.url.path
        if path.startswith("/challenges"):
            data = {"titre": "Example", "score": "10", "url_challenge": CHALLENGE}
            return httpx.Response(200, json=[data, {"rel": "self", "href": str(request.url)}])
        if path.startswith("/auteurs/2"):
            data = {"nom": "Example", "id_auteur": "2", "score": "10", "position": "4"}
            return httpx.Response(200, json=[data, {"rel": "self", "href": str(request.url)}])
        return httpx.Response(200, text=challenge_html)

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
    html = (fixture_html / "challenge.html").read_text(encoding="utf-8")
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
        assert Category.WEB_SERVER in client.list_categories()
        assert client.download("https://repository.root-me.org/file") == b"file"
        target = tmp_path / "file"
        assert client.download(Resource("https://repository.root-me.org/file"), target) == b"file"
        assert target.read_bytes() == b"file"
        assert client.download("https://repository.root-me.org/a/file", tmp_path) == b"file"
        assert (tmp_path / "file").read_bytes() == b"file"


def test_download_files_writes_only_challenge_files(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.host == "static.root-me.org"
        assert request.headers["cookie"] == ""
        return httpx.Response(200, content=request.url.path.encode())

    challenge = Challenge(
        7,
        "Example",
        resources=(Resource("https://repository.root-me.org/doc.pdf"),),
        files=(
            Resource("https://static.root-me.org/a/ch1.zip"),
            Resource("https://static.root-me.org/b/ch1.pcap"),
        ),
    )
    target = tmp_path / "new" / "41"
    with RootMeClient(
        spip_session="test-session", transport=httpx.MockTransport(handler)
    ) as client:
        assert client.download_files(challenge, target) == (target / "ch1.zip", target / "ch1.pcap")
        assert client.download_files(Challenge(8, "Empty"), tmp_path / "empty") == ()
    assert (target / "ch1.zip").read_bytes() == b"/a/ch1.zip"
    assert sorted(p.name for p in target.iterdir()) == ["ch1.pcap", "ch1.zip"]


def test_download_files_reads_a_challenge_reference_into_the_current_directory(
    fixture_html: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    html = (fixture_html / "challenge.html").read_text(encoding="utf-8")

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "api.www.root-me.org":
            return httpx.Response(200, json={"titre": "Example", "url_challenge": CHALLENGE})
        if request.url.host == "static.root-me.org":
            return httpx.Response(200, content=b"synthetic-archive")
        return httpx.Response(200, text=html)

    monkeypatch.chdir(tmp_path)
    with RootMeClient(
        spip_session="test-session", transport=httpx.MockTransport(handler)
    ) as client:
        assert client.download_files(7) == (Path("ch7.zip"),)
        assert client.download_files(CHALLENGE, "by-url") == (Path("by-url/ch7.zip"),)
    assert (tmp_path / "ch7.zip").read_bytes() == b"synthetic-archive"
    assert (tmp_path / "by-url" / "ch7.zip").read_bytes() == b"synthetic-archive"


def test_download_files_rejects_unsafe_names_before_writing(tmp_path: Path) -> None:
    challenge = Challenge(7, "Example", files=(Resource("https://static.root-me.org/a/.."),))
    with RootMeClient() as client, pytest.raises(ValueError):
        client.download_files(challenge, tmp_path / "out")
    assert not (tmp_path / "out").exists()


def test_managed_browser_login_and_reconnection_cleanup(monkeypatch: pytest.MonkeyPatch) -> None:
    browser = MagicMock()
    factory = MagicMock(return_value=browser)
    monkeypatch.setattr("rootme_sdk.authentication.browser.BrowserSession", factory)
    state = Session()
    browser.authenticate.return_value = state
    with RootMeClient(session=state) as client:
        assert client.login("Example", "synthetic-password") == state
        assert client.login("Example", "synthetic-password") == state
        assert browser.close.call_count == 1
    assert browser.close.call_count == 2
    browser.authenticate.side_effect = AuthenticationRequiredError("failed")
    with RootMeClient() as client, pytest.raises(AuthenticationRequiredError):
        client.login("Example", "synthetic-password")
    assert browser.close.call_count == 3


@pytest.mark.parametrize("use_file", [False, True])
def test_constructor_credentials_manage_js_login(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, use_file: bool
) -> None:
    browser = MagicMock()
    browser.authenticate.side_effect = lambda username, password: Session()
    factory = MagicMock(return_value=browser)
    monkeypatch.setattr("rootme_sdk.authentication.browser.BrowserSession", factory)
    server = MagicMock(
        return_value=httpx.Response(
            200,
            text='<div id="anubis_challenge"></div>',
            headers={"set-cookie": "spip_session=anonymous; Path=/"},
        )
    )
    options = {"transport": httpx.MockTransport(server)}
    if use_file:
        source = tmp_path / "credentials.json"
        source.write_text(json.dumps({"login": "Example", "password": "synthetic-password"}))
        options["credentials_file"] = source
        client = RootMeClient(**options)
    else:
        client = RootMeClient("Example", "synthetic-password", **options)
    with client:
        browser.authenticate.assert_called_once_with("Example", "synthetic-password")
        factory.assert_called_once_with(client.session, timeout=180)
        assert server.call_count == 0
        assert client.session.cookies == ()
        assert not hasattr(client, "password") and not hasattr(client.session, "password")
    browser.close.assert_called_once()


def test_constructor_authentication_failure_releases_http_pool(
    monkeypatch: pytest.MonkeyPatch, fixture_html: Path
) -> None:
    close = MagicMock()
    monkeypatch.setattr("rootme_sdk.transport.Transport.close", close)
    login = (fixture_html / "login.html").read_text(encoding="utf-8")
    server = MagicMock(return_value=httpx.Response(200, text=login))
    browser = MagicMock()
    browser.authenticate.side_effect = AuthenticationRequiredError("Login rejected.")
    monkeypatch.setattr(
        "rootme_sdk.authentication.browser.BrowserSession", lambda *args, **kw: browser
    )
    with pytest.raises(AuthenticationRequiredError):
        RootMeClient("Example", "synthetic-password", transport=httpx.MockTransport(server))
    close.assert_called_once()


@pytest.mark.parametrize("session,cookie", [(Session(), None), (None, ""), (None, "synthetic")])
def test_constructor_rejects_mixed_credentials(session: Session | None, cookie: str | None) -> None:
    with pytest.raises(ValueError):
        RootMeClient("Example", "synthetic-password", session=session, spip_session=cookie)


def test_new_login_discards_old_browser_session(
    monkeypatch: pytest.MonkeyPatch, fixture_html: Path
) -> None:
    browser = MagicMock()
    monkeypatch.setattr(
        "rootme_sdk.authentication.browser.BrowserSession", lambda *args, **kw: browser
    )
    server = MagicMock(return_value=httpx.Response(200, text='<div id="anubis_version"></div>'))
    browser.request.return_value = httpx.Response(
        200,
        text=(fixture_html / "challenge.html").read_text(encoding="utf-8"),
        request=httpx.Request("GET", CHALLENGE),
    )
    with RootMeClient(spip_session="old-session", transport=httpx.MockTransport(server)) as client:
        client.read_challenge(CHALLENGE)
        client.login("Example", "synthetic-password")
        browser.close.assert_called_once()
        assert client.session.spip_session is None


def test_failed_login_erases_partial_authentication(monkeypatch: pytest.MonkeyPatch) -> None:
    browser = MagicMock()
    state = Session()

    def fail(username: str, password: str) -> None:
        state.cookies = (SessionCookie("spip_session", "anonymous"),)
        raise AuthenticationRequiredError("Login rejected.")

    browser.authenticate.side_effect = fail
    monkeypatch.setattr(
        "rootme_sdk.authentication.browser.BrowserSession", lambda *args, **kw: browser
    )
    with RootMeClient(session=state) as client:
        with pytest.raises(AuthenticationRequiredError):
            client.login("Example", "synthetic-password")
        assert state.cookies == ()
    browser.close.assert_called_once()


def test_public_js_reads_are_automatic_and_browser_gate_is_not_replayed(
    monkeypatch: pytest.MonkeyPatch, fixture_html: Path
) -> None:
    browser = MagicMock()
    monkeypatch.setattr(
        "rootme_sdk.authentication.browser.BrowserSession", lambda *args, **kw: browser
    )
    server = MagicMock(return_value=httpx.Response(200, text='<div id="anubis_version"></div>'))
    with RootMeClient(transport=httpx.MockTransport(server)) as client:
        browser.request.return_value = httpx.Response(
            200,
            text=(fixture_html / "challenge.html").read_text(encoding="utf-8"),
            request=httpx.Request("GET", CHALLENGE),
        )
        assert client.read_challenge(CHALLENGE).score == 10
        browser.prepare.assert_called_once()
        browser.request.return_value = httpx.Response(
            200, text='<div id="anubis_version"></div>', request=httpx.Request("GET", CHALLENGE)
        )
        with pytest.raises(HumanInterventionRequiredError):
            client.read_challenge(CHALLENGE)
        browser.prepare.assert_called_once()


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
    html = (fixture_html / "preferences.html").read_text(encoding="utf-8")
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
    html = (fixture_html / "challenge.html").read_text(encoding="utf-8")
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


def test_challenge_query_filters_and_validation() -> None:
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, json=[{"0": {"titre": "First"}}])

    with RootMeClient(
        spip_session="test-session", transport=httpx.MockTransport(handler)
    ) as client:
        items = list(
            client.iter_challenges(
                title="Web",
                subtitle="Intro",
                language="fr",
                score=25,
                author_ids=[10, 20],
                tri="date",
            )
        )
        assert len(items) == 1
        params = calls[-1].url.params
        assert params["titre"] == "Web"
        assert params["soustitre"] == "Intro"
        assert params["lang"] == "fr"
        assert params["score"] == "25"
        assert params.get_list("id_auteur[]") == ["10", "20"]
        assert params["tri"] == "date"

        client.list_challenges(score=5, tri="points")
        assert calls[-1].url.params["score"] == "5"
        assert calls[-1].url.params["tri"] == "points"

        client.list_challenges(lang="en")
        assert calls[-1].url.params["lang"] == "en"

        with pytest.raises(ValueError, match="Supply either language or lang"):
            client.list_challenges(language="fr", lang="en")
        with pytest.raises(ValueError, match="Language"):
            list(client.iter_challenges(language="invalid"))
        with pytest.raises(ValueError, match="Identifier"):
            list(client.iter_challenges(author_ids=[-1]))


def test_collection_endpoints_treat_404_as_empty_results() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json=[{"error": {"code": 404}}])

    with RootMeClient(
        spip_session="test-session", transport=httpx.MockTransport(handler)
    ) as client:
        result = client.list_challenges(score=5, lang="en")
        assert result.items == ()
        assert result.next_url is None
        assert list(client.iter_challenges(score=5, lang="en")) == []
        with pytest.raises(NotFoundError):
            client.get_challenge(999)


def test_lazy_pagination_terminates_on_404_continuation() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.params.get("page") == "2":
            return httpx.Response(404, json=[{"error": {"code": 404}}])
        return httpx.Response(
            200,
            json=[{"0": {"titre": "First"}}, {"rel": "next", "href": API + "/challenges?page=2"}],
        )

    with RootMeClient(
        spip_session="test-session", transport=httpx.MockTransport(handler)
    ) as client:
        iterator = client.iter_challenges(score=5)
        assert [c.title for c in iterator] == ["First"]


def test_search_challenges_validation() -> None:
    client = RootMeClient(
        spip_session="test-session", transport=httpx.MockTransport(lambda r: httpx.Response(200))
    )
    with pytest.raises(ValueError, match="Limit"):
        list(client.search_challenges(limit=0))
    with pytest.raises(ValueError, match="Score"):
        list(client.search_challenges(score=-1))
    # Contradictory difficulty and score yields empty iterator
    assert list(client.search_challenges(difficulty=Difficulty.HARD, score=5)) == []


def test_search_challenges_filtering_and_pagination() -> None:
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if request.url.params.get("debut_challenges") == "2":
            return httpx.Response(
                200,
                json=[
                    {
                        "0": {
                            "id_challenge": "3",
                            "titre": "Web 3",
                            "id_rubrique": "68",
                            "score": "5",
                        }
                    }
                ],
            )
        return httpx.Response(
            200,
            json=[
                {"0": {"id_challenge": "1", "titre": "Web 1", "id_rubrique": "68", "score": "5"}},
                {"1": {"id_challenge": "2", "titre": "Web 2", "id_rubrique": "68", "score": "50"}},
                {"rel": "next", "href": API + "/challenges?debut_challenges=2"},
            ],
        )

    with RootMeClient(
        spip_session="test-session", transport=httpx.MockTransport(handler)
    ) as client:
        results = list(
            client.search_challenges(
                query="Web",
                category=Category.WEB_SERVER,
                difficulty=Difficulty.VERY_EASY,
                score=5,
                limit=2,
            )
        )
        assert len(results) == 2
        assert results[0].id == 1 and results[0].difficulty == Difficulty.VERY_EASY
        assert results[1].id == 3 and results[1].category == Category.WEB_SERVER
        assert calls[0].url.params["id_rubrique"] == "68"
        assert calls[0].url.params["titre"] == "Web"
        assert calls[0].url.params["score"] == "5"


def test_search_challenges_by_difficulty_and_unfiltered() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        score = request.url.params.get("score")
        if score == "5":
            return httpx.Response(200, json=[{"0": {"id_challenge": "10", "titre": "C10"}}])
        if score == "10":
            return httpx.Response(200, json=[{"0": {"id_challenge": "11", "titre": "C11"}}])
        return httpx.Response(200, json=[{"0": {"id_challenge": "20", "titre": "C20"}}])

    with RootMeClient(
        spip_session="test-session", transport=httpx.MockTransport(handler)
    ) as client:
        # Search by difficulty (fetches score=5 then score=10)
        by_diff = list(client.search_challenges(difficulty=Difficulty.VERY_EASY, limit=2))
        assert len(by_diff) == 2
        assert by_diff[0].score == 5 and by_diff[0].difficulty == Difficulty.VERY_EASY
        assert by_diff[1].score == 10 and by_diff[1].difficulty == Difficulty.VERY_EASY

        # Search unfiltered with default limit
        unfiltered = list(client.search_challenges(limit=1))
        assert len(unfiltered) == 1
        assert unfiltered[0].id == 20 and unfiltered[0].score is None


def test_submit_flag_delegates_to_submit_answer() -> None:
    html = (
        '<div class="tile"><h1 class="challenge-titre-7">Test</h1>'
        '<span class="challenge-score-7">10</span><div class="t-body">Body</div>'
        '<form id="formulaire_validation_challenge" action="' + CHALLENGE + '" method="post">'
        '<input type="hidden" name="formulaire_action" value="validation_challenge"/>'
        '<input type="text" name="passe" value=""/>'
        '<input type="submit" name="submit" value="valider"/>'
        "</form></div>"
    )
    ok_html = (
        '<div id="formulaire_validation_challenge">'
        '<div class="reponse_formulaire_ok">Bravo !</div></div>'
    )

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "api.www.root-me.org":
            return httpx.Response(200, json={"titre": "Test", "url_challenge": CHALLENGE})
        if request.method == "POST":
            return httpx.Response(200, text=ok_html)
        return httpx.Response(200, text=html)

    with RootMeClient(
        spip_session="test-session", transport=httpx.MockTransport(handler)
    ) as client:
        result = client.submit_flag(7, "flag{test}")
        assert result.status == SubmissionStatus.ACCEPTED


def test_get_profile_authenticated_and_explicit_user() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        uid = request.url.path.split("/")[-1]
        data = {
            "id_auteur": uid,
            "nom": "User" + uid,
            "score": "150",
            "position": "10",
            "validations": {"0": {"id_challenge": "5"}},
        }
        return httpx.Response(200, json=[data, {"rel": "self", "href": str(request.url)}])

    with RootMeClient(
        spip_session="779366_testtoken", transport=httpx.MockTransport(handler)
    ) as client:
        profile = client.get_profile()
        assert profile.id == 779366
        assert profile.username == "User779366"
        assert profile.score == 150
        assert profile.rank == 10
        assert profile.solved_challenges_count == 1
        other = client.get_profile(42)
        assert other.id == 42

    with (
        RootMeClient(transport=httpx.MockTransport(handler)) as anonymous,
        pytest.raises(AuthenticationRequiredError),
    ):
        anonymous.get_profile()

    with (
        RootMeClient(spip_session="badtoken", transport=httpx.MockTransport(handler)) as invalid,
        pytest.raises(UnexpectedResponseError),
    ):
        invalid.get_profile()


def test_get_challenge_corrects_solved_status_via_cache(fixture_html: Path) -> None:
    """Report account progression even when the challenge page lacks a solved marker."""
    challenge_html = (fixture_html / "challenge.html").read_text(encoding="utf-8")
    profile_data = {
        "id_auteur": "779366",
        "nom": "Test",
        "score": "100",
        "position": "1",
        "validations": {"0": {"id_challenge": "7"}},
    }

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "api.www.root-me.org":
            path = request.url.path
            if path.startswith("/challenges"):
                return httpx.Response(
                    200,
                    json=[
                        {"titre": "Example", "score": "10", "url_challenge": CHALLENGE},
                        {"rel": "self", "href": str(request.url)},
                    ],
                )
            # /auteurs/779366
            return httpx.Response(
                200, json=[profile_data, {"rel": "self", "href": str(request.url)}]
            )
        # Web page: no solved marker -> ch.solved will be False from HTML
        return httpx.Response(200, text=challenge_html)

    with RootMeClient(
        spip_session="779366_testtoken", transport=httpx.MockTransport(handler)
    ) as client:
        # Pre-populate the cache so _load_user_solved_ids is not called during get_challenge
        client._cached_solved_ids = {7}
        # Pass the URL (str) so cid=None → is_solved=None → challenge_page falls back to HTML
        # detection (returns solved=False since fixture has no success marker) → line 180 triggers
        ch = client.get_challenge(CHALLENGE)
        # The cache override must flip solved to True (line 180)
        assert ch.solved is True


def test_load_user_solved_ids_happy_path() -> None:
    """Cover client.py lines 207-209: _load_user_solved_ids when profile returns validations."""
    profile_data = {
        "id_auteur": "779366",
        "nom": "Test",
        "score": "50",
        "position": "5",
        "validations": {"0": {"id_challenge": "42"}, "1": {"id_challenge": "99"}},
    }

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=[profile_data, {"rel": "self", "href": str(request.url)}])

    with RootMeClient(
        spip_session="779366_testtoken", transport=httpx.MockTransport(handler)
    ) as client:
        solved = client._user_solved_ids
        assert 42 in solved and 99 in solved
        # Second access uses the cache (no extra call expected)
        assert client._user_solved_ids is solved


@pytest.mark.parametrize(
    "validations", [True, "invalid", [{"id_challenge": True}], [{"unexpected": "value"}]]
)
def test_invalid_progression_data_is_reported(validations: object) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"nom": "Example", "validations": validations})

    with RootMeClient(
        spip_session="42_synthetic", transport=httpx.MockTransport(handler)
    ) as client:
        with pytest.raises(UnexpectedResponseError):
            _ = client._user_solved_ids
        assert client._cached_solved_ids is None


def test_progression_authentication_failure_is_not_reported_as_unsolved() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401)

    with RootMeClient(
        spip_session="42_synthetic", transport=httpx.MockTransport(handler)
    ) as client:
        with pytest.raises(AuthenticationRequiredError):
            _ = client._user_solved_ids
        assert client._cached_solved_ids is None


def test_successful_submission_invalidates_progression_without_extra_reads(
    fixture_html: Path,
) -> None:
    challenge_html = (fixture_html / "challenge.html").read_text(encoding="utf-8")
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if request.method == "POST":
            return httpx.Response(
                200,
                text='<div id="formulaire_validation_challenge"><p class="success">'
                "Validated</p></div>",
            )
        return httpx.Response(200, text=challenge_html)

    with RootMeClient(
        spip_session="42_synthetic", transport=httpx.MockTransport(handler)
    ) as client:
        client._cached_solved_ids = {1}
        assert (
            client.submit_answer(CHALLENGE, "synthetic-answer").status == SubmissionStatus.ACCEPTED
        )
        assert client._cached_solved_ids is None
    assert [request.method for request in calls] == ["GET", "GET", "POST"]
    assert all(request.url.host == "www.root-me.org" for request in calls)
