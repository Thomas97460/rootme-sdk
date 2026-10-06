"""Platform and resource-level error classes."""


class RootMeError(Exception):
    """Base error for all SDK failures."""


class NotFoundError(RootMeError):
    """The requested platform resource does not exist."""


class UnexpectedResponseError(RootMeError):
    """The platform response does not match a supported format."""
