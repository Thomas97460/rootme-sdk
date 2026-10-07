import pytest

from rootme_sdk.transport import pacing
from rootme_sdk.transport.pacing import RequestPacer


def test_negative_interval_is_rejected() -> None:
    with pytest.raises(ValueError, match="negative"):
        RequestPacer(-1)


def test_first_request_is_immediate_then_spaced(paced_waits: list[float]) -> None:
    pacer = RequestPacer(2)
    pacer.pace()
    assert paced_waits == []
    pacer.pace()
    pacer.pace()
    assert paced_waits == [2, 2]


def test_elapsed_time_counts_toward_the_interval(
    monkeypatch: pytest.MonkeyPatch, paced_waits: list[float]
) -> None:
    clock = [10.0]
    monkeypatch.setattr(pacing, "monotonic", lambda: clock[0])
    pacer = RequestPacer(2)
    pacer.pace()
    clock[0] = 11.5
    pacer.pace()
    assert paced_waits == [0.5]
    clock[0] = 20.0
    pacer.pace()
    assert paced_waits == [0.5]


def test_zero_interval_disables_pacing(paced_waits: list[float]) -> None:
    pacer = RequestPacer(0)
    pacer.pace()
    pacer.pace()
    assert paced_waits == []
