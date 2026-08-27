"""Challenge contract tests for 02_long_horizon."""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

CHALLENGE_ROOT = Path(__file__).parents[2] / "challenges" / "02_long_horizon"
FIXTURE_ROOT = CHALLENGE_ROOT / "fixture"
GRADER_ROOT = CHALLENGE_ROOT / "grader"


def _run_sim(tmp_path: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(FIXTURE_ROOT / "service_sim.py"), "--db", str(tmp_path / "service.db"), *args],
        capture_output=True,
        text=True,
    )


def test_same_seed_yields_same_fault_sequence(tmp_path: Path) -> None:
    """Determinism: same seed produces the same sequence of events."""
    _run_sim(tmp_path, "--init")
    for _ in range(2):
        _run_sim(tmp_path, "--fault", "invalid_config")
    _run_sim(tmp_path, "--recover")
    result = _run_sim(tmp_path, "--health")
    assert result.returncode == 0


def test_oracle_recovery_passes_grader(tmp_path: Path) -> None:
    """An oracle agent initializes, processes missions, and recovers."""
    shutil.copy(FIXTURE_ROOT / "controls" / "oracle_solution.py", tmp_path / "service_sim.py")

    result = subprocess.run(
        [sys.executable, "-m", "pytest", str(GRADER_ROOT / "test_recovery.py"), "-q"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0


def test_restart_only_fails_corrupted_checkpoint(tmp_path: Path) -> None:
    """A restart-only handler cannot pass when the checkpoint is corrupted."""
    _run_sim(tmp_path, "--init")
    _run_sim(tmp_path, "--fault", "crash_after_checkpoint")
    _run_sim(tmp_path, "--recover")  # restart-only baseline
    shutil.copy(FIXTURE_ROOT / "service_sim.py", tmp_path / "service_sim.py")

    result = subprocess.run(
        [sys.executable, "-m", "pytest", str(GRADER_ROOT / "test_recovery.py"), "-q"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
