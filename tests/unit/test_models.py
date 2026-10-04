from rootme_sdk import (
    Category,
    Challenge,
    Collection,
    Environment,
    FormField,
    RankingEntry,
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
    assert Category("Example", resource.url).title == "Example"
    assert Environment(1, "Example", {}).data == {}
    assert RankingEntry(1, "Example", 10).score == 10
    assert UserProfile(1, "Example", 10, 1, {}).position == 1
    collection = Collection((resource,), None)
    assert collection.items == (resource,) and collection.next_url is None
    field = FormField("password", "password", "synthetic-password")
    form = WebForm(resource.url, resource.url, "POST", "login", (field,))
    document = WebPage(resource.url, "Example", "synthetic-secret", (), (form,), "synthetic-secret")
    upload = Upload("test.txt", b"synthetic-secret")
    result = SubmissionResult(SubmissionStatus.ACCEPTED, "synthetic-secret")
    for data in (field, form, document, upload, result):
        assert "synthetic-secret" not in repr(data) and "synthetic-password" not in repr(data)
