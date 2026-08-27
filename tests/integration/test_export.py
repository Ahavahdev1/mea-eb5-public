"""Tests for producing the engineer-visible repository."""

from pathlib import Path

from scripts.export_participant_repo import export_participant_repo


PROJECT_ROOT = Path(__file__).parents[2]


def test_export_contains_runner_but_no_private_grader_or_controls(tmp_path: Path) -> None:
    destination = tmp_path / "mea-eb5-runner"

    export_participant_repo(PROJECT_ROOT, destination)

    assert (destination / ".github" / "workflows" / "benchmark.yml").is_file()
    assert (destination / "src" / "mea_eb5" / "runner.py").is_file()
    assert len(list((destination / "challenges").glob("*/challenge.yaml"))) == 5
    paths = [path.relative_to(destination).parts for path in destination.rglob("*")]
    assert all("grader" not in parts for parts in paths)
    assert all("controls" not in parts for parts in paths)
    assert not (destination / ".github" / "workflows" / "grade.yml").exists()
    assert not (destination / ".github" / "workflows" / "publish.yml").exists()
    assert not list(destination.rglob("*.egg-info"))
    assert (destination / "uv.lock").is_file()
    assert (destination / ".gitignore").is_file()


def test_exported_challenge_manifests_do_not_reference_private_paths(tmp_path: Path) -> None:
    destination = tmp_path / "mea-eb5-runner"
    export_participant_repo(PROJECT_ROOT, destination)

    for manifest in destination.glob("challenges/*/challenge.yaml"):
        text = manifest.read_text(encoding="utf-8")
        assert "grader_root" not in text
        assert "controls" not in text
