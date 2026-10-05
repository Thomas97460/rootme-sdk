from rootme_sdk import (
    Category,
    Challenge,
    ChallengeSummary,
    Collection,
    Difficulty,
    FormField,
    Resource,
    SubmissionResult,
    SubmissionStatus,
    Upload,
    UserProfile,
    WebForm,
    WebPage,
)


def test_public_typed_results_and_redacted_repr() -> None:
    resource = Resource("https://www.root-me.org/file", "File")
    assert Challenge(7, "Example", resources=(resource,)).resources == (resource,)
    assert Category.WEB_SERVER == "web-server"
    assert Category.WEB_SERVER.label == "Web - Serveur"
    assert Difficulty.VERY_EASY == "very-easy"
    summary = ChallengeSummary(7, "Example", Category.WEB_SERVER, Difficulty.VERY_EASY, 5)
    assert summary.id == 7 and summary.category == Category.WEB_SERVER
    profile = UserProfile(1, "Example", 10, 1, rank=1, solved_challenges_count=5)
    assert profile.position == 1 and profile.username == "Example" and profile.rank == 1
    collection = Collection((resource,), None)
    assert collection.items == (resource,) and collection.next_url is None
    field = FormField("password", "password", "synthetic-password")
    form = WebForm(resource.url, resource.url, "POST", "login", (field,))
    document = WebPage(resource.url, "Example", "synthetic-secret", (), (form,), "synthetic-secret")
    upload = Upload("test.txt", b"synthetic-secret")
    result = SubmissionResult(SubmissionStatus.ACCEPTED, "synthetic-secret")
    for data in (field, form, document, upload, result):
        assert "synthetic-secret" not in repr(data) and "synthetic-password" not in repr(data)
