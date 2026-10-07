from rootme_sdk.errors.network import NetworkError, RateLimitedError
from rootme_sdk.errors.platform import RootMeError


def test_network_errors() -> None:
    assert isinstance(NetworkError("failed"), RootMeError)
    rate_limited = RateLimitedError(5.0)
    assert isinstance(rate_limited, RootMeError)
    assert rate_limited.retry_after == 5.0
    assert RateLimitedError(None).retry_after is None


def test_rate_limit_message_reports_the_waiting_interval() -> None:
    assert str(RateLimitedError(41.2)) == "Root-Me rate limit reached; retry after 42 s."
    assert str(RateLimitedError(0)) == "Root-Me rate limit reached; retry after 0 s."
    assert str(RateLimitedError(None)) == "Root-Me rate limit reached; no Retry-After provided."
