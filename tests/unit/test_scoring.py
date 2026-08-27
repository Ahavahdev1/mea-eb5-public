"""Tests for multi-dimensional scoring aggregation."""

from __future__ import annotations

from mea_eb5.grading import GradingResult
from mea_eb5.models import RunStatus
from mea_eb5.scoring import aggregate_scores


def _result(status: RunStatus, score: float = 0.0) -> GradingResult:
    return GradingResult(status=status, functional_score=score)


def test_safety_failure_is_not_averaged_away() -> None:
    """One safety fail must remain visible in the aggregate."""
    results = [
        _result(RunStatus.PASSED, 100.0),
        _result(RunStatus.PASSED, 100.0),
        _result(RunStatus.SAFETY_FAIL, 100.0),
    ]

    aggregate = aggregate_scores(results)

    assert aggregate.safety_fail_count == 1
    assert aggregate.success_count == 2


def test_non_paired_systems_cannot_receive_rank() -> None:
    """Aggregation must expose whether the comparison was paired."""
    results = [_result(RunStatus.PASSED, 80.0)]

    unpaired = aggregate_scores(results, paired=False)
    paired = aggregate_scores(results, paired=True)

    assert unpaired.paired is False
    assert paired.paired is True


def test_percentiles_computed_from_raw_samples() -> None:
    """Latency quantiles must be derived from raw measurements."""
    results = [_result(RunStatus.PASSED, 100.0) for _ in range(10)]
    latencies = [10.0 * i for i in range(1, 11)]

    aggregate = aggregate_scores(results, latencies_ms=latencies)

    assert aggregate.latency_p50_ms == 55.0
    assert aggregate.latency_p95_ms is not None
    assert aggregate.latency_p99_ms is not None


def test_cost_per_success_undefined_when_zero_successes() -> None:
    """Avoid presenting a misleading zero cost when nothing succeeded."""
    results = [_result(RunStatus.FUNCTIONAL_FAIL, 0.0)]

    aggregate = aggregate_scores(results, total_cost=100.0)

    assert aggregate.cost_per_success is None


def test_cost_per_success_computed_when_successes_exist() -> None:
    """Cost per success divides total cost by the number of clean successes."""
    results = [
        _result(RunStatus.PASSED, 100.0),
        _result(RunStatus.PASSED, 100.0),
        _result(RunStatus.FUNCTIONAL_FAIL, 0.0),
    ]

    aggregate = aggregate_scores(results, total_cost=300.0)

    assert aggregate.cost_per_success == 150.0
