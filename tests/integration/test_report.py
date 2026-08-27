"""Integration tests for the report builder."""

from __future__ import annotations

import json
from pathlib import Path

from scripts.build_report import build_report


def test_build_report_creates_index_json_and_html(tmp_path: Path) -> None:
    runs_dir = tmp_path / "runs"
    runs_dir.mkdir()
    run_dir = runs_dir / "run-001"
    run_dir.mkdir()
    manifest = {
        "run_id": "run-001",
        "status": "PASSED",
        "config": {"challenge_id": "01", "adapter": "noop"},
        "seed": 0,
        "schema_version": "1.0",
        "started_at": "2026-01-01T00:00:00Z",
        "finished_at": "2026-01-01T00:00:01Z",
        "artifact_hashes": {"manifest.json": "c" * 64},
        "git_commit": "a" * 40,
        "images": {"benchmark": "sha256:" + "b" * 64},
        "adapter_version": "1.0",
        "versions": {"mea-eb5": "0.1.0"},
        "network_allowed": False,
    }
    (run_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    output_dir = tmp_path / "reports"
    build_report(runs_dir, output_dir)

    assert (output_dir / "index.json").exists()
    assert (output_dir / "index.html").exists()

    data = json.loads((output_dir / "index.json").read_text(encoding="utf-8"))
    assert data["count"] == 1
    assert data["runs"][0]["run_id"] == "run-001"


def test_report_uses_private_grade_status_and_metrics(tmp_path: Path) -> None:
    """Published results must come from score.json, not the ungraded manifest."""
    run_dir = tmp_path / "evaluated" / "run-001"
    run_dir.mkdir(parents=True)
    (run_dir / "manifest.json").write_text(
        json.dumps(
            {
                "run_id": "run-001",
                "status": "FUNCTIONAL_FAIL",
                "config": {"challenge_id": "03_self_improvement", "adapter": "cli"},
                "seed": 0,
            }
        ),
        encoding="utf-8",
    )
    (run_dir / "score.json").write_text(
        json.dumps(
            {
                "run_id": "run-001",
                "status": "PASSED",
                "functional_score": 100.0,
                "metrics": [{"name": "performance_gain", "value": 3.2, "unit": "ratio"}],
                "grader_provenance": "INDEPENDENT",
            }
        ),
        encoding="utf-8",
    )

    output = tmp_path / "report"
    build_report(tmp_path / "evaluated", output)
    run = json.loads((output / "index.json").read_text(encoding="utf-8"))["runs"][0]

    assert run["status"] == "PASSED"
    assert run["score"]["metrics"][0]["value"] == 3.2
    summary = json.loads((output / "index.json").read_text(encoding="utf-8"))[
        "summary_by_challenge"
    ]["03_self_improvement"]
    assert summary["attempts"] == 1
    assert summary["passed"] == 1
    assert summary["pass_rate"] == 1.0
    assert summary["performance_gain_median"] == 3.2
