"""Client-side spacing between platform requests to stay below Root-Me rate limits."""

from time import monotonic, sleep


class RequestPacer:
    """Keep a minimum interval between the starts of consecutive requests."""

    def __init__(self, interval: float) -> None:
        """Space requests by ``interval`` seconds; zero disables pacing."""
        if interval < 0:
            raise ValueError("The minimum request interval cannot be negative.")
        self.interval = interval
        self._last: float | None = None

    def pace(self) -> None:
        """Wait until the interval since the previous request start has elapsed."""
        now = monotonic()
        if self._last is not None and self._last + self.interval > now:
            sleep(self._last + self.interval - now)
            now = monotonic()
        self._last = now
