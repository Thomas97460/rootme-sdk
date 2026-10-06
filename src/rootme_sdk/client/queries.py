"""Query construction and form resolution for client operations."""

from collections.abc import Mapping, Sequence

import httpx

from ..errors import AuthenticationRequiredError, UnexpectedResponseError
from ..models import WebForm, WebPage


def find_form(document: WebPage, name: str) -> WebForm:
    """Resolve a current form by its observed SPIP action or HTML identifier."""
    matches = [form for form in document.forms if form.name == name]
    if len(matches) == 1:
        return matches[0]
    if any(form.name == "login" for form in document.forms):
        raise AuthenticationRequiredError(
            "Page requires an authenticated web session.", reason="rejected"
        )
    raise UnexpectedResponseError("Expected form is missing or ambiguous.")


def validate_identifier(identifier: int) -> None:
    """Reject nonpositive IDs, including booleans masquerading as integers."""
    if type(identifier) is not int or identifier <= 0:
        raise ValueError("Identifier must be a positive integer.")


def validate_language(language: str) -> None:
    """Validate a simple platform language code at the caller boundary."""
    if len(language) != 2 or not language.isascii() or not language.isalpha():
        raise ValueError("Language must be a two-letter code.")


def build_query(values: Mapping[str, str | int | None]) -> httpx.QueryParams:
    """Omit absent API filters without dropping zero-valued filters."""
    return httpx.QueryParams({key: value for key, value in values.items() if value is not None})


def challenge_query(
    *,
    title: str | None = None,
    subtitle: str | None = None,
    language: str | None = None,
    lang: str | None = None,
    score: int | None = None,
    author_ids: Sequence[int] = (),
    **extra_filters: str | int,
) -> httpx.QueryParams:
    """Build query parameters for challenge listing and lazy iteration.

    Args:
        title: Substring matching the challenge title.
        subtitle: Substring matching the challenge subtitle.
        language: Two-letter language code filter ("en" or "fr").
        lang: Alias for language matching the Root-Me API parameter name.
        score: Exact challenge point score filter.
        author_ids: Sequence of author IDs who created the challenge.
        **extra_filters: Additional raw query parameters sent to the API.

    Returns:
        httpx.QueryParams: Serialized and validated query parameters.
    """
    if language is not None and lang is not None and language != lang:
        raise ValueError("Supply either language or lang, not conflicting values.")
    selected = language if language is not None else lang
    if selected is not None:
        validate_language(selected)
    for identifier in author_ids:
        validate_identifier(identifier)
    params = build_query({"titre": title, "soustitre": subtitle, "lang": selected, "score": score})
    pairs = list(params.multi_items()) + [("id_auteur[]", str(i)) for i in author_ids]
    for key, value in extra_filters.items():
        pairs.append((key, str(value)))
    return httpx.QueryParams(tuple(pairs))
