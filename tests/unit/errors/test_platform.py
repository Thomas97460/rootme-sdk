from rootme_sdk.errors.platform import NotFoundError, RootMeError, UnexpectedResponseError


def test_platform_errors() -> None:
    assert isinstance(RootMeError("base"), Exception)
    assert isinstance(NotFoundError("not found"), RootMeError)
    assert isinstance(UnexpectedResponseError("unexpected"), RootMeError)
