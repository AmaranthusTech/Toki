from __future__ import annotations

from dataclasses import dataclass
import time


@dataclass(frozen=True)
class BenchReport:
    iterations: int
    elapsed_sec: float
    per_iteration_ms: float


def run_bench_smoke(iterations: int = 10_000) -> BenchReport:
    start = time.perf_counter()
    total = 0
    for i in range(iterations):
        total += i
    elapsed = time.perf_counter() - start
    _ = total
    per_iteration_ms = (elapsed / iterations) * 1000
    return BenchReport(
        iterations=iterations,
        elapsed_sec=elapsed,
        per_iteration_ms=per_iteration_ms,
    )
