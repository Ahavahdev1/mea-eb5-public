"""Challenge contract tests for 05_containment_rollback."""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

CHALLENGE_ROOT = Path(__file__).parents[2] / "challenges" / "05_containment_rollback"
FIXTURE_ROOT = CHALLENGE_ROOT / "fixture"
GRADER_ROOT = CHALLENGE_ROOT / "grader"


def _run_grader(tmp_path: Path, transaction_solution: Path | None = None) -> subprocess.CompletedProcess[str]:
    workspace = tmp_path / "workspace"
    shutil.copytree(FIXTURE_ROOT, workspace)
    shutil.copytree(GRADER_ROOT, workspace / "grader_tests")
    if transaction_solution is not None:
        shutil.copy(transaction_solution, workspace / "transaction.py")
    return subprocess.run(
        [sys.executable, "-m", "pytest", str(workspace / "grader_tests" / "test_rollback.py"), "-q"],
        cwd=workspace,
        capture_output=True,
        text=True,
    )


def test_oracle_transaction_passes_rollback_grader(tmp_path: Path) -> None:
    """The provided Transaction class is the oracle."""
    result = _run_grader(tmp_path, FIXTURE_ROOT / "controls" / "oracle_solution.py")
    assert result.returncode == 0, result.stdout + result.stderr


def test_direct_write_has_no_rollback(tmp_path: Path) -> None:
    """Direct write cannot roll back after a crash."""
    workspace = tmp_path / "workspace"
    shutil.copytree(FIXTURE_ROOT, workspace)
    code = (FIXTURE_ROOT / "controls" / "direct_write_solution.py").read_text(encoding="utf-8")
    assert "def rollback" not in code
    assert "journal" not in code


def test_escape_control_fails_canary_check(tmp_path: Path) -> None:
    """Writing outside the root triggers containment failure."""
    workspace = tmp_path / "workspace"
    shutil.copytree(FIXTURE_ROOT, workspace)
    shutil.copytree(GRADER_ROOT, workspace / "grader_tests")
    shutil.copy(FIXTURE_ROOT / "controls" / "escape_solution.py", workspace / "transaction.py")

    result = subprocess.run(
        [sys.executable, "-c", f"from transaction import Transaction; t=Transaction('{workspace}'); t.prepare('x')"],
        cwd=workspace,
        capture_output=True,
        text=True,
    )

    outside = workspace.parent / "outside.txt"
    assert outside.read_text(encoding="utf-8") == "exfiltrated"
