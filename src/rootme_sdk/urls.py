"""Exact platform URL validation shared by independent HTTP and browser adapters."""

from urllib.parse import urljoin, urlsplit

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


def website_url(url: str) -> str:
    """Resolve a relative website link without accepting other hosts or insecure URLs."""
    resolved = platform_url(urljoin(f"https://{WEB_HOST}/", url))
    if urlsplit(resolved).hostname != WEB_HOST:
        raise ValueError("Expected a Root-Me website URL.")
    return resolved
