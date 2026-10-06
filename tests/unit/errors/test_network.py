from rootme_sdk.errors.network import NetworkError, RateLimitedError
from rootme_sdk.errors.platform import RootMeError


def test_network_errors() -> None:
    assert isinstance(NetworkError("failed"), RootMeError)
    rate_limited = RateLimitedError(5.0)
    assert isinstance(rate_limited, RootMeError)
    assert rate_limited.retry_after == 5.0
    assert RateLimitedError(None).retry_after is None
