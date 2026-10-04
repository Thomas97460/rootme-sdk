from pathlib import Path

import pytest
from bs4 import BeautifulSoup

from rootme_sdk import (
    AuthenticationRequiredError,
    SubmissionStatus,
    UnexpectedResponseError,
    WebForm,
)
from rootme_sdk.parsers import web

URL = "https://www.root-me.org/en/Challenges/Example/Test"


def test_observed_already_solved_feedback(fixture_html: Path) -> None:
    document = web.page(
        (fixture_html / "submission-already-solved.html").read_text(encoding="utf-8"), URL
    )
    result = web.submission_result(document, "synthetic-answer")
    assert result.status == SubmissionStatus.ALREADY_SOLVED
    assert "déjà les 10 Points" in result.message


def test_unrelated_success_does_not_validate_a_challenge() -> None:
    document = web.page('<form id="login"><p class="success">Logged in</p></form>', URL)
    assert (
        web.submission_result(document, "synthetic-answer").status == SubmissionStatus.INDETERMINATE
    )


@pytest.mark.parametrize(
    "kind,status",
    [("success", SubmissionStatus.ACCEPTED), ("error", SubmissionStatus.REJECTED)],
)
def test_platform_feedback_classes(kind: str, status: SubmissionStatus) -> None:
    document = web.page(
        f'<div id="formulaire_validation_challenge"><p class="{kind}">'
        "Feedback for synthetic-answer</p></div>",
        URL,
    )
    result = web.submission_result(document, "synthetic-answer")
    assert result.status == status and "synthetic-answer" not in result.message


def test_observed_root_base_element() -> None:
    html = (
        '<head><base href="https://www.root-me.org/"></head>'
        '<a href="en/Challenges/Web-Server/">Web - Server</a>'
        '<form action="./?page=preferences"><input name="q"></form>'
    )
    document = web.page(html, URL)
    assert document.links[0].url == "https://www.root-me.org/en/Challenges/Web-Server/"
    assert document.forms[0].action == "https://www.root-me.org/?page=preferences"
    assert document.forms[0].page_url == URL


def test_observed_challenge_structure(fixture_html: Path) -> None:
    document = web.page((fixture_html / "challenge.html").read_text(encoding="utf-8"), URL)
    result = web.challenge_page(document)
    assert result.id == 7 and result.score == 10 and result.title == "Example challenge"
    assert "Read the supplied file" in result.statement
    assert "synthetic-token" not in result.statement_html
    assert "throw new Error" not in result.statement_html
    assert result.resources[0].url == "https://www.root-me.org/files/example.zip"
    assert document.forms[0].name == "validation_challenge"


def test_preferences_successful_controls_and_csrf(fixture_html: Path) -> None:
    form = web.page((fixture_html / "preferences.html").read_text(encoding="utf-8"), URL).forms[0]
    values = web.form_values(form, {"nom": "New", "pays": "FR"})
    assert values["formulaire_action_args"] == "synthetic-token"
    assert values["nom"] == "New" and values["bio"] == "Example biography"
    assert values["lang_auteur"] == "en"
    assert "supprimer_compte" not in values and "disabled" not in values
    assert "avatar" not in values and "Valider" not in values
    assert web.form_values(form, {"Valider": "Save"})["Valider"] == "Save"
    for changes in (
        {"unknown": "x"},
        {"_jeton": "replacement"},
        {"pays": "invalid"},
        {"avatar": "path"},
    ):
        with pytest.raises(ValueError):
            web.form_values(form, changes)


def test_control_defaults_and_link_protocols() -> None:
    document = web.page(
        (
            '<form><input name="q" value="x"><select name="a"><option value="first"'
            '>First</option></select><select name="empty"></select><input name="fla'
            'g" type="checkbox" checked value="on"></form><a href="mailto:example@e'
            'xample.org">Mail</a><a href="/x">Link</a><a href="/x">Link</a>'
        ),
        URL,
    )
    assert document.title == "" and len(document.links) == 1
    assert document.forms[0].name == "form-0" and document.forms[0].method == "GET"
    values = web.form_values(document.forms[0], {})
    assert values["a"] == "first" and values["empty"] == "" and values["flag"] == "on"


@pytest.mark.parametrize(
    "action,method", [("https://api.www.root-me.org/login", "POST"), (URL, "PUT")]
)
def test_refuse_unverified_form_target(action: str, method: str) -> None:
    with pytest.raises(ValueError):
        web.form_values(WebForm(URL, action, method, "test", ()), {})


def test_unexpected_attribute_type() -> None:
    tag = BeautifulSoup("<input>", "html.parser").input
    assert tag is not None
    tag.attrs["name"] = ["invalid"]
    with pytest.raises(UnexpectedResponseError):
        web.attribute(tag, "name")


@pytest.mark.parametrize(
    "html,kind",
    [
        ("<p>Unsupported</p>", UnexpectedResponseError),
        (
            '<form><input type="hidden" name="formulaire_action" value="login"></form>',
            AuthenticationRequiredError,
        ),
        (
            '<h1 class="challenge-titre-7">X</h1><h2 class="challenge-score-">10</h2>',
            UnexpectedResponseError,
        ),
        (
            '<h1 class="challenge-titre-7">X</h1><h2 class="challenge-score-7">No points</h2>',
            UnexpectedResponseError,
        ),
        (
            '<h1 class="challenge-titre-7">X</h1><h2 class="challenge-score-7">10</h2>',
            UnexpectedResponseError,
        ),
        (
            (
                '<div class="tile"><h1 class="challenge-titre-7">X</h1><h2 class="chall'
                'enge-score-7">10</h2></div>'
            ),
            UnexpectedResponseError,
        ),
    ],
)
def test_invalid_challenge_pages(html: str, kind: type[Exception]) -> None:
    with pytest.raises(kind):
        web.challenge_page(web.page(html, URL))


@pytest.mark.parametrize(
    "css,status",
    [
        ("reponse_formulaire_ok", SubmissionStatus.ACCEPTED),
        ("reponse_formulaire_erreur", SubmissionStatus.REJECTED),
    ],
)
def test_submission_feedback_and_redaction(css: str, status: SubmissionStatus) -> None:
    result = web.submission_result(
        web.page(
            f'<div id="formulaire_validation_challenge"><p class="{css}">'
            "Feedback for synthetic-answer</p></div>",
            URL,
        ),
        "synthetic-answer",
    )
    assert result.status == status and "synthetic-answer" not in result.message
    assert (
        web.submission_result(web.page("<p>HTTP 200</p>", URL), "synthetic-answer").status
        == SubmissionStatus.INDETERMINATE
    )
