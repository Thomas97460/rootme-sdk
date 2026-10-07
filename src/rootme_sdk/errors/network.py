"""Network transport and rate-limiting error classes."""

from math import ceil

from .platform import RootMeError


class NetworkError(RootMeError):
    """A bounded request failed without exposing its request contents."""


class RateLimitedError(RootMeError):
    """The server requests that the caller wait before making another request."""

    def __init__(self, retry_after: float | None) -> None:
        """Expose the server's waiting interval, when available, in the error and its message."""
        wait = (
            "no Retry-After provided"
            if retry_after is None
            else f"retry after {ceil(retry_after)} s"
        )
        super().__init__(f"Root-Me rate limit reached; {wait}.")
        self.retry_after = retry_after
