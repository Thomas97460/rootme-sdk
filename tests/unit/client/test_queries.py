from typing import cast

import pytest

from rootme_sdk.client.queries import (
    build_query,
    challenge_query,
    find_form,
    validate_identifier,
    validate_language,
)
from rootme_sdk.errors import AuthenticationRequiredError, UnexpectedResponseError
from rootme_sdk.models import FormField, WebForm, WebPage


def test_find_form() -> None:
    field = FormField("test", "text")
    form1 = WebForm("https://example.com", "https://example.com", "POST", "target", (field,))
    form_login = WebForm("https://example.com", "https://example.com", "POST", "login", (field,))

    page_with_target = WebPage("https://example.com", "Title", "", (), (form1,), "")
    assert find_form(page_with_target, "target") == form1

    page_with_login = WebPage("https://example.com", "Title", "", (), (form_login,), "")
    with pytest.raises(AuthenticationRequiredError):
        find_form(page_with_login, "missing")

    page_empty = WebPage("https://example.com", "Title", "", (), (), "")
    with pytest.raises(UnexpectedResponseError):
        find_form(page_empty, "missing")

    page_duplicate = WebPage("https://example.com", "Title", "", (), (form1, form1), "")
    with pytest.raises(UnexpectedResponseError):
        find_form(page_duplicate, "target")


def test_validate_identifier() -> None:
    validate_identifier(42)
    for bad in (0, -1, -42, True, False, "12"):
        with pytest.raises(ValueError, match="positive integer"):
            validate_identifier(cast(int, bad))


def test_validate_language() -> None:
    validate_language("en")
    validate_language("fr")
    for bad in ("eng", "e", "12", "éé", ""):
        with pytest.raises(ValueError, match="two-letter code"):
            validate_language(bad)


def test_build_query() -> None:
    query = build_query({"a": "hello", "b": None, "c": 0, "d": "world"})
    assert query["a"] == "hello"
    assert "b" not in query
    assert query["c"] == "0"
    assert query["d"] == "world"


def test_challenge_query() -> None:
    params = challenge_query(
        title="SQL",
        subtitle="Injections",
        language="en",
        score=20,
        author_ids=(1, 2),
        custom="extra",
    )
    items = list(params.multi_items())
    assert ("titre", "SQL") in items
    assert ("soustitre", "Injections") in items
    assert ("lang", "en") in items
    assert ("score", "20") in items
    assert ("id_auteur[]", "1") in items
    assert ("id_auteur[]", "2") in items
    assert ("custom", "extra") in items

    params_lang_alias = challenge_query(lang="fr")
    assert params_lang_alias["lang"] == "fr"

    with pytest.raises(ValueError, match="conflicting"):
        challenge_query(language="en", lang="fr")
