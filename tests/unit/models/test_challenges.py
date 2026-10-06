import pytest

from rootme_sdk.models.challenges import (
    CATEGORY_RUBRIQUES,
    DIFFICULTY_SCORES,
    RUBRIQUE_CATEGORIES,
    Category,
    Challenge,
    ChallengeSummary,
    Difficulty,
    Resource,
    SubmissionResult,
    SubmissionStatus,
)


def test_challenges_models() -> None:
    resource = Resource("https://www.root-me.org/file", "File")
    assert resource.title == "File"
    assert "url='https://www.root-me.org/file'" in repr(resource)

    spaced_resource = Resource(
        "https://repository.root-me.org/Programmation/XML - HTML/FR - HTML essentiel.pdf",
        "HTML essentiel",
    )
    assert (
        spaced_resource.url
        == "https://repository.root-me.org/Programmation/XML%20-%20HTML/FR%20-%20HTML%20essentiel.pdf"
    )

    challenge = Challenge(7, "Example", resources=(resource,))
    assert challenge.resources == (resource,) and challenge.files == ()
    assert challenge.id == 7
    assert challenge.title == "Example"

    assert Category.WEB_SERVER == "web-server"
    assert Category.WEB_SERVER.label == "Web - Serveur"
    assert Category.APP_SCRIPT.label == "App - Script"
    assert Difficulty.VERY_EASY == "very-easy"
    assert DIFFICULTY_SCORES[Difficulty.VERY_EASY] == (5, 10)
    assert CATEGORY_RUBRIQUES[Category.WEB_SERVER] == 68
    assert RUBRIQUE_CATEGORIES[68] == Category.WEB_SERVER

    summary = ChallengeSummary(7, "Example", Category.WEB_SERVER, Difficulty.VERY_EASY, 5)
    assert summary.id == 7 and summary.category == Category.WEB_SERVER

    result = SubmissionResult(SubmissionStatus.ACCEPTED, "synthetic-secret")
    assert result.status == SubmissionStatus.ACCEPTED
    assert "synthetic-secret" not in repr(result)


def test_resource_filename_is_the_decoded_last_path_segment() -> None:
    assert Resource("https://static.root-me.org/cracking/ch1/ch1.zip").filename == "ch1.zip"
    assert Resource("https://static.root-me.org/a/my file.pdf?x=1#y").filename == "my file.pdf"


@pytest.mark.parametrize(
    "url",
    [
        "https://static.root-me.org/",
        "https://static.root-me.org/a/..",
        "https://static.root-me.org/a/%2E%2E",
        "https://static.root-me.org/a/..%2Fsecret",
        "https://static.root-me.org/a/..%5Csecret",
        "https://static.root-me.org/a/c%3Aname",
        "https://static.root-me.org/a/nul%00",
    ],
)
def test_resource_filename_rejects_unsafe_names(url: str) -> None:
    with pytest.raises(ValueError, match="file"):
        _ = Resource(url).filename
