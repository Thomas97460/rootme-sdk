"""Classify platform responses consistently across HTTP and native browser requests."""

from datetime import UTC, datetime
from email.utils import parsedate_to_datetime

import httpx

from ..errors import (
    AuthenticationRequiredError,
    HumanInterventionRequiredError,
    NotFoundError,
    PermissionDeniedError,
    RateLimitedError,
    UnexpectedResponseError,
)


def retry_after(value: str | None) -> float | None:
    """Parse both seconds and HTTP-date Retry-After values."""
    if value is None:
        return None
    try:
        return max(0, float(value))
    except ValueError:
        try:
            return max(0, (parsedate_to_datetime(value) - datetime.now(UTC)).total_seconds())
        except (ValueError, TypeError, OverflowError):
            return None


def check_response(response: httpx.Response) -> None:
    """Classify status and browser gates without disclosing server content."""
    content = response.text.lower()
    if (
        "anubis_challenge" in content
        or "anubis_version" in content
        or "cf-chl-" in content
        or "making sure you're not a bot" in content
    ):
        raise HumanInterventionRequiredError(str(response.url.copy_with(query=None)))
    if response.status_code == 401:
        raise AuthenticationRequiredError(
            "Authentication required or session expired.", reason="rejected"
        )
    if response.status_code == 403:
        raise PermissionDeniedError("Root-Me denied access.")
    if response.status_code == 404:
        raise NotFoundError("Root-Me resource not found.")
    if response.status_code == 429:
        raise RateLimitedError(retry_after(response.headers.get("retry-after")))
    if response.is_error:
        raise UnexpectedResponseError(f"Unexpected Root-Me HTTP status {response.status_code}.")
