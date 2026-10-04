from rootme_sdk import (
    AuthenticationRequiredError,
    HumanInterventionRequiredError,
    NetworkError,
    NotFoundError,
    PermissionDeniedError,
    RateLimitedError,
    RootMeError,
    UnexpectedResponseError,
)


def test_public_error_contracts() -> None:
    for kind in (
        AuthenticationRequiredError,
        NetworkError,
        NotFoundError,
        PermissionDeniedError,
        UnexpectedResponseError,
    ):
        assert isinstance(kind("Example"), RootMeError)
    human = HumanInterventionRequiredError("https://www.root-me.org/")
    assert human.url == "https://www.root-me.org/"
    assert RateLimitedError(5).retry_after == 5
    assert RateLimitedError(None).retry_after is None
