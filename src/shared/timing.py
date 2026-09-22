"""Named export timings, recorded in the log and final manifest."""

from contextlib import contextmanager
from time import perf_counter
from src.shared.log import info


class Timings:
    def __init__(self):
        self.seconds: dict[str, float] = {}

    @contextmanager
    def measure(self, name: str):
        started = perf_counter()
        try:
            yield
        finally:
            elapsed = perf_counter() - started
            self.seconds[name] = elapsed
            info(f"Timing {name}: {elapsed:.3f}s")
