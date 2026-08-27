"""Challenge contract tests for 01_novel_repair."""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

CHALLENGE_ROOT = Path(__file__).parents[2] / "challenges" / "01_novel_repair"
FIXTURE_ROOT = CHALLENGE_ROOT / "fixture"
GRADER_ROOT = CHALLENGE_ROOT / "grader"


def _run_pytest(tmp_path: Path, solution: Path, tests: list[Path]) -> subprocess.CompletedProcess[str]:
    """Copy solution into fixture and run selected pytest files."""
    workspace = tmp_path / "workspace"
    shutil.copytree(FIXTURE_ROOT, workspace)
    shutil.copy(solution, workspace / "src" / "orders.py")

    return subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "--tb=short", *[str(t) for t in tests]],
        cwd=workspace,
        capture_output=True,
        text=True,
    )


def test_oracle_passes_public_tests(tmp_path: Path) -> None:
    result = _run_pytest(
        tmp_path,
        FIXTURE_ROOT / "controls" / "oracle_solution.py",
        [FIXTURE_ROOT / "tests" / "test_public.py"],
    )
    assert result.returncode == 0


def test_oracle_passes_hidden_tests(tmp_path: Path) -> None:
    result = _run_pytest(
        tmp_path,
        FIXTURE_ROOT / "controls" / "oracle_solution.py",
        [FIXTURE_ROOT / "tests" / "test_public.py", GRADER_ROOT / "test_hidden.py"],
    )
    assert result.returncode == 0


def test_noop_fails_hidden_tests(tmp_path: Path) -> None:
    result = _run_pytest(
        tmp_path,
        FIXTURE_ROOT / "controls" / "noop_solution.py",
        [GRADER_ROOT / "test_hidden.py"],
    )
    assert result.returncode != 0


def test_hardcoded_fails_renamed_key(tmp_path: Path) -> None:
    result = _run_pytest(
        tmp_path,
        FIXTURE_ROOT / "controls" / "hardcoded_solution.py",
        [GRADER_ROOT / "test_hidden.py"],
    )
    assert result.returncode != 0
