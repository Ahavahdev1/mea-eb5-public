"""Tests for independent grader validation and negative controls."""

from __future__ import annotations

from pathlib import Path

import pytest

from mea_eb5.grading import ControlCase, Grader, GraderControlResult, GradingResult, validate_grader
from mea_eb5.models import RunStatus


class AlwaysPassGrader:
    """Grader that approves everything — reproduces the audited SRE-bench flaw."""

    def grader_id(self) -> str:
        return "always-pass"

    def validate_controls(self) -> bool:
        return True

    def grade(self, solution: Path, task_id: str) -> GradingResult:
        return GradingResult(status=RunStatus.PASSED, functional_score=100.0)


class HonestGrader:
    """Grader that distinguishes controls as expected by tests."""

    def __init__(self, solution_to_status: dict[Path, RunStatus]) -> None:
        self._mapping = solution_to_status

    def grader_id(self) -> str:
        return "honest"

    def validate_controls(self) -> bool:
        return True

    def grade(self, solution: Path, task_id: str) -> GradingResult:
        status = self._mapping.get(solution, RunStatus.FUNCTIONAL_FAIL)
        return GradingResult(
            status=status,
            functional_score=100.0 if status == RunStatus.PASSED else 0.0,
        )


def test_always_pass_grader_is_rejected_by_negative_controls(tmp_path: Path) -> None:
    """A grader that passes missing, noop and incorrect controls is INVALID_GRADER."""
    missing = tmp_path / "missing"
    noop = tmp_path / "noop"
    incorrect = tmp_path / "incorrect"
    unsafe = tmp_path / "unsafe"
    oracle = tmp_path / "oracle"

    controls = {
        "missing": ControlCase("missing", missing, RunStatus.FUNCTIONAL_FAIL),
        "noop": ControlCase("noop", noop, RunStatus.FUNCTIONAL_FAIL),
        "incorrect": ControlCase("incorrect", incorrect, RunStatus.FUNCTIONAL_FAIL),
        "unsafe": ControlCase("unsafe", unsafe, RunStatus.SAFETY_FAIL),
        "oracle": ControlCase("oracle", oracle, RunStatus.PASSED),
    }

    result = validate_grader(AlwaysPassGrader(), controls)

    assert result.valid is False
    assert result.grader_id == "always-pass"
    assert any("missing" in failure for failure in result.failures)
    assert any("noop" in failure for failure in result.failures)
    assert any("incorrect" in failure for failure in result.failures)
    assert any("unsafe" in failure for failure in result.failures)


def test_honest_grader_passes_validation(tmp_path: Path) -> None:
    """A grader that correctly distinguishes controls is accepted."""
    missing = tmp_path / "missing"
    oracle = tmp_path / "oracle"
    controls = {
        "missing": ControlCase("missing", missing, RunStatus.FUNCTIONAL_FAIL),
        "oracle": ControlCase("oracle", oracle, RunStatus.PASSED),
    }
    grader = HonestGrader({missing: RunStatus.FUNCTIONAL_FAIL, oracle: RunStatus.PASSED})

    result = validate_grader(grader, controls)

    assert result.valid is True
    assert result.failures == ()


def test_validation_catches_failing_oracle(tmp_path: Path) -> None:
    """A grader that rejects a known-good oracle is invalid."""
    oracle = tmp_path / "oracle"
    controls = {"oracle": ControlCase("oracle", oracle, RunStatus.PASSED)}
    grader = HonestGrader({oracle: RunStatus.FUNCTIONAL_FAIL})

    result = validate_grader(grader, controls)

    assert result.valid is False
    assert any("oracle" in failure for failure in result.failures)
