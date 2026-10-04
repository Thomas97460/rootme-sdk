import pytest

from rootme_sdk import AuthenticationRequiredError, PermissionDeniedError, UnexpectedResponseError
from rootme_sdk.parsers.api import (
    challenge,
    environment,
    integer,
    json_payload,
    ranking,
    records,
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
    assert environment({"nom": "Example", "id_environnement_virtuel": "6"}).id == 6
    assert environment({"nom": "Example"}, identifier=6).id == 6
    assert ranking({"nom": "Example", "place": "2", "score": "10"}).position == 2
    assert integer({}, "absent") is None and text({}, "absent", default="") == ""


@pytest.mark.parametrize("value", [True, 1.5, "-2", "bad", None])
def test_no_lossy_integer_coercion(value: object) -> None:
    with pytest.raises(UnexpectedResponseError):
        integer({"x": value}, "x", required=True)


def test_invalid_required_text() -> None:
    with pytest.raises(UnexpectedResponseError):
        text({}, "nom")
