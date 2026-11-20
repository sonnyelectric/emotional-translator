"""Content-free counters and timing samples (no transcript text, no audio)."""

from __future__ import annotations

import logging
from collections import defaultdict, deque

log = logging.getLogger(__name__)
MAX_SAMPLES = 2048


def percentile(values: list[float], q: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, round(q * (len(ordered) - 1))))
    return ordered[index]


class Metrics:
    def __init__(self) -> None:
        self.counters: dict[str, int] = defaultdict(int)
        self.timings: dict[str, deque[float]] = defaultdict(lambda: deque(maxlen=MAX_SAMPLES))

    def count(self, name: str, n: int = 1) -> None:
        self.counters[name] += n

    def observe(self, name: str, value_ms: float) -> None:
        self.timings[name].append(value_ms)

    def merge(self, prefix: str, counters: dict[str, int]) -> None:
        for name, value in counters.items():
            self.counters[f"{prefix}.{name}"] = value

    def snapshot(self) -> dict:
        return {
            "counters": dict(self.counters),
            "timings_ms": {
                name: {"n": len(values), "p50": percentile(list(values), 0.5), "p95": percentile(list(values), 0.95)}
                for name, values in self.timings.items()
            },
        }

    def log_summary(self, label: str) -> None:
        log.info("%s metrics: %s", label, self.snapshot())
