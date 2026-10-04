"""Exact platform URL validation shared by independent HTTP and browser adapters."""

from urllib.parse import urlsplit

from .authentication.session import API_HOST, WEB_HOST


def platform_url(url: str) -> str:
    """Validate an HTTPS platform URL without user-info or alternate ports."""
    parts = urlsplit(url)
    if (
        parts.scheme != "https"
        or parts.hostname not in {WEB_HOST, API_HOST}
        or parts.username
        or parts.password
        or parts.port not in {None, 443}
    ):
        raise ValueError("Expected an HTTPS Root-Me platform URL.")
    return url
