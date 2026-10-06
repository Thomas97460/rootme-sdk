"""Network transport and rate-limiting error classes."""

from .platform import RootMeError


class NetworkError(RootMeError):
    """A bounded request failed without exposing its request contents."""


class RateLimitedError(RootMeError):
    """The server requests that the caller wait before making another request."""

    def __init__(self, retry_after: float | None) -> None:
        """Expose the server's waiting interval, when available."""
        super().__init__("Root-Me rate limit reached.")
        self.retry_after = retry_after
