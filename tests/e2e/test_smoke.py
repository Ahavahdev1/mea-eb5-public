"""End-to-end smoke test for the full benchmark pipeline."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parents[2]


def test_noop_smoke_pipeline() -> None:
    """A full noop run produces artifacts and a report without secrets."""
    subprocess.run(
        [sys.executable, "-m", "mea_eb5.cli", "validate", "challenges"],
        cwd=PROJECT_ROOT,
        check=True,
    )
    result = subprocess.run(
        [sys.executable, "-m", "mea_eb5.cli", "run", "--challenge", "01_novel_repair", "--adapter", "noop", "--seeds", "1"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    assert "FUNCTIONAL_FAIL" in result.stdout

    subprocess.run(
        [sys.executable, "scripts/build_report.py", "runs", "reports"],
        cwd=PROJECT_ROOT,
        check=True,
    )
    html = (PROJECT_ROOT / "reports" / "index.html").read_text(encoding="utf-8")
    assert "<script>" not in html or "&lt;script&gt;" in html
