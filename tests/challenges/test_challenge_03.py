"""Challenge contract tests for 03_self_improvement."""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

CHALLENGE_ROOT = Path(__file__).parents[2] / "challenges" / "03_self_improvement"
FIXTURE_ROOT = CHALLENGE_ROOT / "fixture"
GRADER_ROOT = CHALLENGE_ROOT / "grader"


def _run_with_solution(tmp_path: Path, solution: Path) -> subprocess.CompletedProcess[str]:
    workspace = tmp_path / "workspace"
    shutil.copytree(FIXTURE_ROOT, workspace)
    shutil.copy(solution, workspace / "event_index.py")
    return subprocess.run(
        [sys.executable, str(GRADER_ROOT / "benchmark.py")],
        cwd=workspace,
        capture_output=True,
        text=True,
    )


def test_oracle_passes_and_achieves_gain(tmp_path: Path) -> None:
    result = _run_with_solution(tmp_path, FIXTURE_ROOT / "controls" / "oracle_solution.py")
    assert result.returncode == 0, result.stdout + result.stderr
    assert '"passed": true' in result.stdout


def test_cached_public_solution_fails_hidden(tmp_path: Path) -> None:
    result = _run_with_solution(tmp_path, FIXTURE_ROOT / "controls" / "cached_solution.py")
    assert result.returncode != 0


def test_skipped_inputs_fails_correctness(tmp_path: Path) -> None:
    result = _run_with_solution(tmp_path, FIXTURE_ROOT / "controls" / "skipped_solution.py")
    assert result.returncode != 0


def test_baseline_is_quadratic_and_fails_gain(tmp_path: Path) -> None:
    """The original quadratic baseline must fail the 2x gain threshold."""
    result = _run_with_solution(tmp_path, FIXTURE_ROOT / "event_index.py")
    assert result.returncode != 0
