import pytest

from rootme_sdk.transport.urls import platform_url, sanitize_url, website_url

WEB = "https://www.root-me.org/"


@pytest.mark.parametrize(
    "url",
    [
        "http://www.root-me.org/",
        "https://evil.example/",
        "https://user:pass@www.root-me.org/",
        "https://www.root-me.org:444/",
    ],
)
def test_platform_origin_validation(url: str) -> None:
    with pytest.raises(ValueError):
        platform_url(url)
    assert platform_url(WEB) == WEB


@pytest.mark.parametrize(
    "reference",
    [
        "fr/Challenges/Example/Test",
        "/fr/Challenges/Example/Test",
        WEB + "fr/Challenges/Example/Test",
    ],
)
def test_relative_website_urls(reference: str) -> None:
    assert website_url(reference) == WEB + "fr/Challenges/Example/Test"


@pytest.mark.parametrize(
    "reference",
    [
        "https://evil.example/",
        "//evil.example/",
        "https://api.www.root-me.org/challenges",
        "http://www.root-me.org/",
    ],
)
def test_website_origin_is_preserved(reference: str) -> None:
    with pytest.raises(ValueError):
        website_url(reference)


@pytest.mark.parametrize(
    "raw,expected",
    [
        (
            "https://repository.root-me.org/Programmation/XML - HTML/FR - HTML essentiel.pdf",
            "https://repository.root-me.org/Programmation/XML%20-%20HTML/FR%20-%20HTML%20essentiel.pdf",
        ),
        (
            "https://repository.root-me.org/Programmation/XML%20-%20HTML/FR%20-%20HTML%20essentiel.pdf",
            "https://repository.root-me.org/Programmation/XML%20-%20HTML/FR%20-%20HTML%20essentiel.pdf",
        ),
        (
            "https://repository.root-me.org/RFC/EN - rfc1945.txt",
            "https://repository.root-me.org/RFC/EN%20-%20rfc1945.txt",
        ),
        (
            "https://repository.root-me.org/Programmation/XML - HTML/",
            "https://repository.root-me.org/Programmation/XML%20-%20HTML/",
        ),
        (
            "  https://example.com/test?query=hello world&foo=bar#section 1  ",
            "https://example.com/test?query=hello%20world&foo=bar#section%201",
        ),
        (
            "/files/my doc.pdf",
            "/files/my%20doc.pdf",
        ),
    ],
)
def test_sanitize_url(raw: str, expected: str) -> None:
    assert sanitize_url(raw) == expected
