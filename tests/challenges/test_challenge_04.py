"""Challenge contract tests for 04_adversarial_security."""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

CHALLENGE_ROOT = Path(__file__).parents[2] / "challenges" / "04_adversarial_security"
FIXTURE_ROOT = CHALLENGE_ROOT / "fixture"
GRADER_ROOT = CHALLENGE_ROOT / "grader"


def _run_with_solution(tmp_path: Path, solution: Path) -> subprocess.CompletedProcess[str]:
    workspace = tmp_path / "workspace"
    shutil.copytree(FIXTURE_ROOT, workspace)
    shutil.copy(solution, workspace / "auth_service.py")
    return subprocess.run(
        [sys.executable, "-m", "pytest", str(GRADER_ROOT / "test_security.py"), "-q"],
        cwd=workspace,
        capture_output=True,
        text=True,
    )


def test_oracle_passes_security_suite(tmp_path: Path) -> None:
    result = _run_with_solution(tmp_path, FIXTURE_ROOT / "controls" / "oracle_solution.py")
    assert result.returncode == 0, result.stdout + result.stderr


def test_refuse_all_is_safe_but_fails_utility(tmp_path: Path) -> None:
    result = _run_with_solution(tmp_path, FIXTURE_ROOT / "controls" / "refuse_all_solution.py")
    # Refuse-all blocks IDOR but also blocks legitimate owner access.
    assert "invalid session" in result.stdout or result.returncode != 0


def test_vulnerable_solution_fails_security(tmp_path: Path) -> None:
    result = _run_with_solution(tmp_path, FIXTURE_ROOT / "controls" / "vulnerable_solution.py")
    assert result.returncode != 0


def test_injection_following_solution_fails_security(tmp_path: Path) -> None:
    result = _run_with_solution(tmp_path, FIXTURE_ROOT / "controls" / "injection_following_solution.py")
    assert result.returncode != 0
