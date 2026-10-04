"""Public errors with messages that never include response bodies or credentials."""

from typing import Literal


class RootMeError(Exception):
    """Base error for all SDK failures."""


class AuthenticationRequiredError(RootMeError):
    """The requested operation needs authentication or an expired session renewed."""

    def __init__(
        self, message: str, *, reason: Literal["missing", "expired", "rejected"] = "missing"
    ) -> None:
        """Distinguish absent state, local expiry and platform-rejected credentials."""
        super().__init__(message)
        self.reason = reason


class PermissionDeniedError(RootMeError):
    """The platform denied the operation with the supplied credentials."""


class NotFoundError(RootMeError):
    """The requested platform resource does not exist."""


class UnexpectedResponseError(RootMeError):
    """The platform response does not match a supported format."""


class NetworkError(RootMeError):
    """A bounded request failed without exposing its request contents."""


class HumanInterventionRequiredError(RootMeError):
    """A browser or human verification is required before retrying the operation."""

    def __init__(self, url: str) -> None:
        """Record the safe page URL at which verification should take place."""
        super().__init__("Browser verification required; import its session and retry.")
        self.url = url


class RateLimitedError(RootMeError):
    """The server requests that the caller wait before making another request."""

    def __init__(self, retry_after: float | None) -> None:
        """Expose the server's waiting interval, when available."""
        super().__init__("Root-Me rate limit reached.")
        self.retry_after = retry_after
