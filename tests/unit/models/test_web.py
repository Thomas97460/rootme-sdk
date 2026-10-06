from rootme_sdk.models.challenges import Resource
from rootme_sdk.models.web import FormField, Upload, WebForm, WebPage


def test_web_models_and_redaction() -> None:
    resource = Resource("https://www.root-me.org/file", "File")
    field = FormField("password", "password", "synthetic-password")
    assert field.name == "password"
    assert field.kind == "password"
    assert field.value == "synthetic-password"

    form = WebForm(resource.url, resource.url, "POST", "login", (field,))
    assert form.page_url == resource.url
    assert form.method == "POST"
    assert form.name == "login"

    document = WebPage(
        resource.url, "Example", "synthetic-secret", (resource,), (form,), "synthetic-secret"
    )
    assert document.title == "Example"
    assert document.url == resource.url

    upload = Upload("test.txt", b"synthetic-secret")
    assert upload.filename == "test.txt"
    assert upload.content == b"synthetic-secret"
    assert upload.content_type == "application/octet-stream"

    for data in (field, form, document, upload):
        assert "synthetic-secret" not in repr(data) and "synthetic-password" not in repr(data)
