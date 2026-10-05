import pytest

from rootme_sdk import (
    AuthenticationRequiredError,
    Category,
    Difficulty,
    PermissionDeniedError,
    UnexpectedResponseError,
)
from rootme_sdk.parsers.api import (
    challenge,
    challenge_summary,
    integer,
    json_payload,
    records,
    score_to_difficulty,
    text,
    user,
)


def test_observed_detail_and_indexed_collection_shapes() -> None:
    payload = json_payload(
        '[{"titre":"Example","score":"10"},{"rel":"next","href":"https://api.ww'
        'w.root-me.org/challenges/7?debut=10"}]'
    )
    result = records(payload)
    assert len(result) == 1
    assert challenge(result[0], identifier=7).score == 10
    assert records([{"0": {"nom": "Example"}}]) == [{"nom": "Example"}]
    assert records({}) == []
    assert json_payload("false") is False
    with pytest.raises(UnexpectedResponseError):
        records(False)


@pytest.mark.parametrize(
    "payload,kind",
    [
        ("invalid", UnexpectedResponseError),
        ('[{"error":{"code":401}}]', AuthenticationRequiredError),
        ('{"error":{"code":"403"}}', PermissionDeniedError),
        ('{"error":"bad"}', UnexpectedResponseError),
        ('{"error":{"code":500}}', UnexpectedResponseError),
    ],
)
def test_api_error_envelopes(payload: str, kind: type[Exception]) -> None:
    with pytest.raises(kind):
        json_payload(payload)


def test_record_models_preserve_extra_data() -> None:
    result = challenge(
        {
            "titre": "Test",
            "id_challenge": "7",
            "score": 10,
            "id_rubrique": "3",
            "descriptif": "<p>Read <b>this</b></p>",
            "url_challenge": "https://www.root-me.org/en/Challenges/Example/Test",
            "difficulte": "1",
        }
    )
    assert result.id == 7 and result.score == 10 and result.category_id == 3
    assert result.statement == "Read\nthis" and result.data["difficulte"] == "1"
    assert user({"nom": "Example", "score": "10", "position": 3}, identifier=4).id == 4
    assert user({"nom": "Example", "id_auteur": "8"}).id == 8
    assert integer({}, "absent") is None and text({}, "absent", default="") == ""


@pytest.mark.parametrize("value", [True, 1.5, "-2", "bad", None])
def test_no_lossy_integer_coercion(value: object) -> None:
    with pytest.raises(UnexpectedResponseError):
        integer({"x": value}, "x", required=True)


def test_invalid_required_text() -> None:
    with pytest.raises(UnexpectedResponseError):
        text({}, "nom")


def test_relative_challenge_links_from_api() -> None:
    assert (
        challenge({"titre": "Example", "url_challenge": "fr/Challenges/Example/Test"}).url
        == "https://www.root-me.org/fr/Challenges/Example/Test"
    )
    assert challenge({"titre": "Example"}).url is None
    with pytest.raises(UnexpectedResponseError, match="invalid challenge URL"):
        challenge({"titre": "Example", "url_challenge": "//evil.example/"})


def test_score_to_difficulty_mapping() -> None:
    assert score_to_difficulty(None) is None
    assert score_to_difficulty(5) == Difficulty.VERY_EASY
    assert score_to_difficulty(10) == Difficulty.VERY_EASY
    assert score_to_difficulty(15) == Difficulty.EASY
    assert score_to_difficulty(20) == Difficulty.EASY
    assert score_to_difficulty(25) == Difficulty.MEDIUM
    assert score_to_difficulty(35) == Difficulty.MEDIUM
    assert score_to_difficulty(40) == Difficulty.HARD
    assert score_to_difficulty(50) == Difficulty.HARD
    assert score_to_difficulty(75) == Difficulty.VERY_HARD


def test_challenge_summary_parsing() -> None:
    record = {
        "id_challenge": "5",
        "titre": "HTML",
        "id_rubrique": "68",
        "score": "5",
        "url_challenge": "fr/Challenges/Web-Serveur/HTML",
    }
    summary = challenge_summary(record)
    assert summary.id == 5
    assert summary.title == "HTML"
    assert summary.category == Category.WEB_SERVER
    assert summary.difficulty == Difficulty.VERY_EASY
    assert summary.score == 5
    assert summary.url == "https://www.root-me.org/fr/Challenges/Web-Serveur/HTML"

    with pytest.raises(UnexpectedResponseError, match="Missing challenge identifier"):
        challenge_summary({"titre": "HTML"})
