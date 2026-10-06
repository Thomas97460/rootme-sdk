from rootme_sdk.errors.authentication import (
    AuthenticationRequiredError,
    BrowserUnavailableError,
    HumanInterventionRequiredError,
    PermissionDeniedError,
)
from rootme_sdk.errors.platform import RootMeError


def test_authentication_errors() -> None:
    assert isinstance(BrowserUnavailableError("unavailable"), RootMeError)
    assert isinstance(PermissionDeniedError("denied"), RootMeError)
    auth = AuthenticationRequiredError("auth required", reason="expired")
    assert isinstance(auth, RootMeError)
    assert auth.reason == "expired"
    default_auth = AuthenticationRequiredError("auth required")
    assert default_auth.reason == "missing"
    human = HumanInterventionRequiredError("https://www.root-me.org/")
    assert isinstance(human, RootMeError)
    assert human.url == "https://www.root-me.org/"
    assert "Root-Me browser verification did not complete." in str(human)
