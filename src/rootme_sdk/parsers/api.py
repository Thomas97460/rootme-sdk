"""Validate official API data at the external boundary."""

import json
from typing import cast

from bs4 import BeautifulSoup

from ..errors import AuthenticationRequiredError, PermissionDeniedError, UnexpectedResponseError
from ..models import Challenge, Environment, JSONObject, JSONValue, RankingEntry, UserProfile


def json_payload(content: str) -> JSONValue:
    """Decode JSON and detect API errors carried by successful HTTP responses."""
    try:
        data = cast(JSONValue, json.loads(content))
    except ValueError:
        raise UnexpectedResponseError("Root-Me API returned invalid JSON.") from None
    candidates = data if isinstance(data, list) else [data]
    for item in candidates:
        if isinstance(item, dict) and "error" in item:
            error = item["error"]
            code = error.get("code") if isinstance(error, dict) else None
            if str(code) == "401":
                raise AuthenticationRequiredError(
                    "Root-Me API authentication required.", reason="rejected"
                )
            if str(code) == "403":
                raise PermissionDeniedError("Root-Me API access denied.")
            raise UnexpectedResponseError("Root-Me API reported an error.")
    return data


def records(data: JSONValue) -> list[JSONObject]:
    """Normalize indexed objects and lists, excluding explicit API pagination links."""
    if isinstance(data, list):
        return [record for item in data for record in records(item)]
    if not isinstance(data, dict):
        raise UnexpectedResponseError("Expected an API collection.")
    if not data or set(data) == {"rel", "href"}:
        return []
    if all(key.isdecimal() for key in data):
        return [record for item in data.values() for record in records(item)]
    return [data]


def integer(data: JSONObject, key: str, *, required: bool = False) -> int | None:
    """Read an integer or decimal string, rejecting booleans and lossy coercion."""
    value = data.get(key)
    if value is None and not required:
        return None
    if type(value) is int:
        return value
    if isinstance(value, str) and value.isdecimal():
        return int(value)
    raise UnexpectedResponseError("Invalid integer in Root-Me data.")


def text(data: JSONObject, key: str, *, default: str | None = None) -> str:
    """Read a text field, requiring it unless a default is explicitly provided."""
    value = data.get(key, default)
    if not isinstance(value, str):
        raise UnexpectedResponseError("Missing or invalid text in Root-Me data.")
    return value


def challenge(data: JSONObject, *, identifier: int | None = None) -> Challenge:
    """Build a challenge while retaining any additional fields in data."""
    html = text(data, "descriptif", default="")
    return Challenge(
        integer(data, "id_challenge") or identifier,
        text(data, "titre"),
        integer(data, "score"),
        integer(data, "id_rubrique"),
        text(data, "url_challenge", default="") or None,
        html,
        BeautifulSoup(html, "html.parser").get_text("\n", strip=True),
        data=data,
    )


def user(data: JSONObject, *, identifier: int | None = None) -> UserProfile:
    """Build a user profile from official API fields."""
    return UserProfile(
        integer(data, "id_auteur") or identifier,
        text(data, "nom"),
        integer(data, "score"),
        integer(data, "position"),
        data,
    )


def environment(data: JSONObject, *, identifier: int | None = None) -> Environment:
    """Build an environment while preserving undocumented details as data."""
    return Environment(
        integer(data, "id_environnement_virtuel") or identifier, text(data, "nom"), data
    )


def ranking(data: JSONObject) -> RankingEntry:
    """Read a ranking row with all documented fields required."""
    position, score = integer(data, "place", required=True), integer(data, "score", required=True)
    assert position is not None and score is not None
    return RankingEntry(position, text(data, "nom"), score)
