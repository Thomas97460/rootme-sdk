import socket
from pathlib import Path

import pytest

from rootme_sdk.transport import pacing


@pytest.fixture(autouse=True)
def offline(monkeypatch: pytest.MonkeyPatch) -> None:
    def reject(*args: object, **kwargs: object) -> None:
        raise AssertionError("Automated tests must not access the network")

    monkeypatch.setattr(socket.socket, "connect", reject)
    monkeypatch.setattr(socket.socket, "connect_ex", reject)


@pytest.fixture(autouse=True)
def paced_waits(monkeypatch: pytest.MonkeyPatch) -> list[float]:
    """Advance a virtual clock instead of sleeping between paced requests."""
    clock = [0.0]
    waits: list[float] = []

    def wait(seconds: float) -> None:
        waits.append(seconds)
        clock[0] += seconds

    monkeypatch.setattr(pacing, "monotonic", lambda: clock[0])
    monkeypatch.setattr(pacing, "sleep", wait)
    return waits


@pytest.fixture
def fixture_html() -> Path:
    return Path(__file__).parent / "fixtures"
