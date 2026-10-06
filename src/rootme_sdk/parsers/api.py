"""Validate official API data at the external boundary."""

import json
from typing import cast

from bs4 import BeautifulSoup

from ..errors import AuthenticationRequiredError, PermissionDeniedError, UnexpectedResponseError
from ..models import (
    RUBRIQUE_CATEGORIES,
    Challenge,
    ChallengeSummary,
    Difficulty,
    JSONObject,
    JSONValue,
    UserProfile,
)
from ..transport import website_url


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


def score_to_difficulty(score: int | None) -> Difficulty | None:
    """Map a numerical point score to a standardized difficulty level."""
    if score is None:
        return None
    if score <= 10:
        return Difficulty.VERY_EASY
    if score <= 20:
        return Difficulty.EASY
    if score <= 35:
        return Difficulty.MEDIUM
    if score <= 50:
        return Difficulty.HARD
    return Difficulty.VERY_HARD


def challenge(data: JSONObject, *, identifier: int | None = None) -> Challenge:
    """Build a challenge while retaining any additional fields in data."""
    html = text(data, "descriptif", default="")
    rubrique_id = integer(data, "id_rubrique")
    score_val = integer(data, "score")
    raw_authors = records(data.get("auteurs", []))
    authors = tuple(text(a, "nom") for a in raw_authors if isinstance(a, dict) and "nom" in a)
    validations = data.get("validations")
    val_count = len(validations) if isinstance(validations, (list, dict)) else None
    return Challenge(
        integer(data, "id_challenge") or identifier,
        text(data, "titre"),
        category=RUBRIQUE_CATEGORIES.get(rubrique_id) if rubrique_id else None,
        difficulty=score_to_difficulty(score_val),
        score=score_val,
        category_id=rubrique_id,
        url=_challenge_link(data),
        statement_html=html,
        statement=BeautifulSoup(html, "html.parser").get_text("\n", strip=True),
        authors=authors,
        date=text(data, "date_publication", default="") or None,
        validations_count=val_count,
        data=data,
    )


def challenge_summary(data: JSONObject, *, default_score: int | None = None) -> ChallengeSummary:
    """Build a challenge summary from listing records."""
    rubrique_id = integer(data, "id_rubrique")
    score_val = integer(data, "score") or default_score
    cid = integer(data, "id_challenge")
    if cid is None:
        raise UnexpectedResponseError("Missing challenge identifier in listing record.")
    return ChallengeSummary(
        id=cid,
        title=text(data, "titre"),
        category=RUBRIQUE_CATEGORIES.get(rubrique_id) if rubrique_id else None,
        difficulty=score_to_difficulty(score_val),
        score=score_val,
        url=_challenge_link(data),
    )


def _challenge_link(data: JSONObject) -> str | None:
    """Normalize observed relative API links while rejecting malformed destinations."""
    url = text(data, "url_challenge", default="")
    if not url:
        return None
    try:
        return website_url(url)
    except ValueError:
        raise UnexpectedResponseError("Root-Me returned an invalid challenge URL.") from None


def user(data: JSONObject, *, identifier: int | None = None) -> UserProfile:
    """Build a user profile from official API fields."""
    validations = data.get("validations")
    val_count = len(validations) if isinstance(validations, (list, dict)) else 0
    # Accounts without points are unranked and report an empty position.
    pos = None if data.get("position") == "" else integer(data, "position")
    return UserProfile(
        id=integer(data, "id_auteur") or identifier,
        name=text(data, "nom"),
        score=integer(data, "score"),
        position=pos,
        rank=pos,
        solved_challenges_count=val_count,
        data=data,
    )
