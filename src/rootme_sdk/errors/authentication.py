"""Authentication and interactive verification error classes."""

from typing import Literal

from .platform import RootMeError


class BrowserUnavailableError(RootMeError):
    """The required headed browser or graphical display could not be prepared."""


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


class HumanInterventionRequiredError(RootMeError):
    """A browser or human verification is required before retrying the operation."""

    def __init__(self, url: str) -> None:
        """Record the safe page URL at which verification should take place."""
        super().__init__("Root-Me browser verification did not complete.")
        self.url = url
