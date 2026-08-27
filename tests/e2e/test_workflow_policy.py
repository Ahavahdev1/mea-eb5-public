"""Policy tests for GitHub Actions workflows."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

WORKFLOWS = Path(__file__).parents[2] / ".github" / "workflows"


@pytest.mark.parametrize("workflow", ["ci.yml", "benchmark.yml", "grade.yml", "publish.yml"])
def test_workflow_uses_pinned_actions(workflow: str) -> None:
    path = WORKFLOWS / workflow
    text = path.read_text(encoding="utf-8")
    assert "uses: actions/" in text
    for line in text.splitlines():
        if "uses: actions/" in line:
            assert "@" in line


def test_no_pull_request_target() -> None:
    for path in WORKFLOWS.iterdir():
        text = path.read_text(encoding="utf-8")
        assert "pull_request_target" not in text


def test_benchmark_job_has_read_only_permissions() -> None:
    path = WORKFLOWS / "benchmark.yml"
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert data.get("permissions") == {"contents": "read"}


def test_benchmark_parallelizes_five_challenges_and_release_seeds() -> None:
    data = yaml.safe_load((WORKFLOWS / "benchmark.yml").read_text(encoding="utf-8"))
    matrix = data["jobs"]["attempt"]["strategy"]["matrix"]
    assert len(matrix["challenge"]) == 5
    assert matrix["seed"] == [0, 1, 2, 3, 4]
    assert data["jobs"]["attempt"]["strategy"]["max-parallel"] >= 5


def test_attempt_workflow_is_ungraded_secretless_and_retained_for_14_days() -> None:
    text = (WORKFLOWS / "benchmark.yml").read_text(encoding="utf-8")
    runner_script = (WORKFLOWS.parents[1] / "scripts" / "run_attempt_job.sh").read_text(
        encoding="utf-8"
    )
    assert "--attempt-only" in runner_script
    assert "retention-days: 14" in text
    assert "secrets." not in text
    assert "${{ github.event.inputs" not in text


def test_grade_consumes_an_explicit_cross_run_artifact_and_retains_90_days() -> None:
    text = (WORKFLOWS / "grade.yml").read_text(encoding="utf-8")
    assert "run-id:" in text
    assert "repository:" in text
    assert "retention-days: 90" in text
    assert "environment: private-grader" in text
    assert "docker build" in text
    assert "--network none" in text
    assert "--read-only" in text
    assert "--cap-drop ALL" in text


def test_private_grader_image_uses_a_digest_pinned_base() -> None:
    dockerfile = (WORKFLOWS.parents[1] / "Dockerfile.grader").read_text(encoding="utf-8")
    first_line = dockerfile.splitlines()[0]
    assert first_line.startswith("FROM python:3.12-slim@sha256:")
    assert len(first_line.rsplit("sha256:", 1)[1]) == 64


def test_publish_only_downloads_evaluated_bundles() -> None:
    text = (WORKFLOWS / "publish.yml").read_text(encoding="utf-8")
    assert "grade_run_id" in text
    assert "evaluated-" in text
    assert "attempt-" not in text
