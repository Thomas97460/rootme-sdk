"""Exact platform URL validation shared by independent HTTP and browser adapters."""

from urllib.parse import quote, urljoin, urlsplit, urlunsplit

from ..authentication.session import API_HOST, WEB_HOST

STATIC_HOST = "static.root-me.org"
_PATH_SAFE = "/:@!$&'()*+,;=%~_-"
_QUERY_SAFE = "&;=+%~_-?:@!$'()*,"
_FRAG_SAFE = "/:@!$&'()*+,;=%~_-?"


def sanitize_url(url: str) -> str:
    """Encode unescaped characters in a URL while preserving valid structure and encoding."""
    parts = urlsplit(url.strip())
    encoded_path = quote(parts.path, safe=_PATH_SAFE)
    encoded_query = quote(parts.query, safe=_QUERY_SAFE) if parts.query else ""
    encoded_frag = quote(parts.fragment, safe=_FRAG_SAFE) if parts.fragment else ""
    return urlunsplit((parts.scheme, parts.netloc, encoded_path, encoded_query, encoded_frag))


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
