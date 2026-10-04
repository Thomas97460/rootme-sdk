import pytest

from rootme_sdk.urls import platform_url

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
