"""Integration tests for the mea-eb5 CLI."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
import json
import shutil

import pytest

PROJECT_ROOT = Path(__file__).parents[2]


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "mea_eb5.cli", *args],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
    )


def test_validate_detects_valid_challenges() -> None:
    result = _run("validate", str(PROJECT_ROOT / "challenges"))
    assert result.returncode == 0
    assert "OK" in result.stdout


def test_validate_rejects_missing_challenge(tmp_path: Path) -> None:
    result = _run("validate", str(tmp_path))
    assert result.returncode != 0


def test_run_noop_creates_failed_but_complete_run() -> None:
    result = _run("run", "--challenge", "01_novel_repair", "--adapter", "noop", "--seeds", "1")
    assert result.returncode == 0
    assert "FUNCTIONAL_FAIL" in result.stdout


def test_relative_runs_dir_does_not_recurse_into_the_workspace(tmp_path: Path) -> None:
    shutil.copytree(
        PROJECT_ROOT / "challenges" / "01_novel_repair",
        tmp_path / "challenges" / "01_novel_repair",
    )
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "mea_eb5.cli",
            "run",
            "--challenge",
            "01_novel_repair",
            "--adapter",
            "noop",
            "--attempt-only",
            "--runs-dir",
            "runs",
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        env={**__import__("os").environ, "PYTHONPATH": str(PROJECT_ROOT / "src")},
    )

    assert result.returncode == 0, result.stderr
    workspace = next((tmp_path / "runs").glob("*/workspace"))
    assert not (workspace / "runs").exists()


def test_run_cli_adapter_executes_once_per_seed(tmp_path: Path) -> None:
    """A configured MEA command must run once for every requested seed."""
    marker = tmp_path / "invocations.jsonl"
    adapter_config = tmp_path / "mea.adapter.yaml"
    adapter_config.write_text(
        "kind: cli\n"
        "allow_host_execution: true\n"
        "command:\n"
        f"  - {json.dumps(sys.executable)}\n"
        "  - -c\n"
        "  - |\n"
        "      import pathlib, sys\n"
        f"      p = pathlib.Path({str(marker)!r})\n"
        "      p.write_text((p.read_text() if p.exists() else '') + 'run\\n')\n",
        encoding="utf-8",
    )

    result = _run(
        "run",
        "--challenge",
        "01_novel_repair",
        "--adapter",
        "cli",
        "--adapter-config",
        str(adapter_config),
        "--runs-dir",
        str(tmp_path / "runs"),
        "--seeds",
        "3",
    )

    assert result.returncode == 0, result.stderr
    assert marker.read_text(encoding="utf-8").splitlines() == ["run", "run", "run"]
    manifests = sorted((tmp_path / "runs").glob("*/manifest.json"))
    assert [json.loads(path.read_text())["seed"] for path in manifests] == [0, 1, 2]


def test_run_cli_adapter_requires_config() -> None:
    """Selecting the real CLI adapter without configuration must fail closed."""
    result = _run("run", "--challenge", "01_novel_repair", "--adapter", "cli")
    assert result.returncode == 2
    assert "adapter config" in result.stdout.lower()


def test_doctor_validates_container_adapter_without_starting_mea(tmp_path: Path) -> None:
    config = tmp_path / "mea.adapter.yaml"
    config.write_text(
        "kind: cli\n"
        f"image: mea@sha256:{'a' * 64}\n"
        "command: [mea, run]\n",
        encoding="utf-8",
    )

    result = _run("doctor", "--adapter-config", str(config))

    assert result.returncode == 0, result.stderr
    assert "OK" in result.stdout
    assert "network=none" in result.stdout


def test_run_can_start_from_an_explicit_seed_for_parallel_jobs(tmp_path: Path) -> None:
    """Matrix jobs must produce distinct deterministic seed identities."""
    result = _run(
        "run",
        "--challenge",
        "01_novel_repair",
        "--adapter",
        "noop",
        "--runs-dir",
        str(tmp_path / "runs"),
        "--seeds",
        "2",
        "--seed-start",
        "7",
    )

    assert result.returncode == 0, result.stderr
    manifests = sorted((tmp_path / "runs").glob("*/manifest.json"))
    assert sorted(json.loads(path.read_text())["seed"] for path in manifests) == [7, 8]


def test_grade_regrades_a_downloaded_run_without_placeholder_output(tmp_path: Path) -> None:
    """The private grading job must produce an independent score for a run artifact."""
    runs_dir = tmp_path / "runs"
    attempt = _run(
        "run",
        "--challenge",
        "01_novel_repair",
        "--adapter",
        "noop",
        "--runs-dir",
        str(runs_dir),
        "--seeds",
        "1",
    )
    assert attempt.returncode == 0, attempt.stderr
    run_dir = next(path.parent for path in runs_dir.glob("*/manifest.json"))

    result = _run(
        "grade",
        run_dir.name,
        "--runs-dir",
        str(runs_dir),
        "--challenges-dir",
        str(PROJECT_ROOT / "challenges"),
    )

    assert result.returncode == 0, result.stderr
    assert "placeholder" not in result.stdout.lower()
    score = json.loads((run_dir / "score.json").read_text(encoding="utf-8"))
    assert score["grader_provenance"] == "INDEPENDENT"
    assert score["grader_id"].startswith("pytest:")
    hidden_junit = (run_dir / "hidden.junit.xml").read_text(encoding="utf-8")
    assert 'tests="0"' not in hidden_junit


def test_reproduce_verifies_a_frozen_attempt_manifest(tmp_path: Path) -> None:
    runs_dir = tmp_path / "runs"
    attempt = _run(
        "run",
        "--challenge",
        "01_novel_repair",
        "--adapter",
        "noop",
        "--runs-dir",
        str(runs_dir),
        "--attempt-only",
    )
    assert attempt.returncode == 0
    manifest = next(runs_dir.glob("*/manifest.json"))

    result = _run("reproduce", str(manifest))

    assert result.returncode == 0, result.stderr
    assert "VERIFIED" in result.stdout


def test_run_never_copies_oracle_controls_into_the_agent_workspace(tmp_path: Path) -> None:
    """Known-good and gaming controls are private grader material."""
    runs_dir = tmp_path / "runs"
    result = _run(
        "run",
        "--challenge",
        "01_novel_repair",
        "--adapter",
        "noop",
        "--runs-dir",
        str(runs_dir),
    )

    assert result.returncode == 0, result.stderr
    workspace = next(runs_dir.glob("*/workspace"))
    assert not (workspace / "controls").exists()
    assert not list(workspace.rglob("__pycache__"))


def test_attempt_only_never_claims_independent_or_real_grading(tmp_path: Path) -> None:
    """The engineer-visible job collects evidence but cannot award an official score."""
    runs_dir = tmp_path / "runs"
    result = _run(
        "run",
        "--challenge",
        "01_novel_repair",
        "--adapter",
        "noop",
        "--runs-dir",
        str(runs_dir),
        "--attempt-only",
    )

    assert result.returncode == 0, result.stderr
    score = json.loads(next(runs_dir.glob("*/score.json")).read_text(encoding="utf-8"))
    assert score["status"] == "NOT_GRADED"
    assert score["evidence_class"] == "NÃO TESTADA"
    assert score["grader_provenance"] == "SELF_REPORTED"
    assert score["grader_id"] == "attempt-only"
    hidden_junit = next(runs_dir.glob("*/hidden.junit.xml")).read_text(encoding="utf-8")
    assert 'skipped="1"' in hidden_junit


def test_report_escapes_script_payloads(tmp_path: Path) -> None:
    """Report generation must escape agent-provided content."""
    runs_dir = tmp_path / "runs"
    runs_dir.mkdir()
    run_dir = runs_dir / "run-escape"
    run_dir.mkdir()
    manifest = {
        "run_id": "<script>alert('xss')</script>",
        "status": "FUNCTIONAL_FAIL",
        "config": {"challenge_id": "x", "adapter": "noop"},
        "seed": 0,
        "schema_version": "1.0",
        "started_at": "2026-01-01T00:00:00Z",
        "finished_at": "2026-01-01T00:00:01Z",
        "artifact_hashes": {},
        "git_commit": "a" * 40,
        "images": {"benchmark": "sha256:" + "b" * 64},
        "adapter_version": "1.0",
        "versions": {"mea-eb5": "0.1.0"},
        "network_allowed": False,
        "malicious": "<script>alert('xss')</script>",
    }
    (run_dir / "manifest.json").write_text(
        __import__("json").dumps(manifest), encoding="utf-8"
    )

    output_dir = tmp_path / "reports"
    result = _run("report", str(runs_dir), "--output", str(output_dir))
    assert result.returncode == 0

    html_content = (output_dir / "index.html").read_text(encoding="utf-8")
    assert "<script>alert('xss')</script>" not in html_content
    assert "&lt;script&gt;" in html_content
