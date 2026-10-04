import pytest

from rootme_sdk.urls import platform_url, website_url

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
