"""Tests for the private pytest grader wiring."""

from pathlib import Path
import shutil

from mea_eb5.cli import _pytest_grader_factory


def test_pytest_grader_rejects_a_failing_control_contract(tmp_path: Path) -> None:
    """validate_controls must execute the challenge's real control contract."""
    grader_root = tmp_path / "challenges" / "99_example" / "grader"
    grader_root.mkdir(parents=True)
    control_suite = tmp_path / "tests" / "challenges" / "test_challenge_99.py"
    control_suite.parent.mkdir(parents=True)
    control_suite.write_text("def test_control():\n    assert False\n", encoding="utf-8")

    grader = _pytest_grader_factory(grader_root)()

    assert grader.validate_controls() is False


def test_self_improvement_grader_records_hidden_performance_gain(tmp_path: Path) -> None:
    """Challenge 03 must measure speedup, not invoke pytest on a non-test script."""
    project_root = Path(__file__).parents[2]
    challenge_root = project_root / "challenges" / "03_self_improvement"
    workspace = tmp_path / "workspace"
    shutil.copytree(
        challenge_root / "fixture",
        workspace,
        ignore=shutil.ignore_patterns("controls", "__pycache__", "*.pyc"),
    )
    shutil.copy2(
        challenge_root / "fixture" / "controls" / "oracle_solution.py",
        workspace / "event_index.py",
    )
    grader = _pytest_grader_factory(challenge_root / "grader")()

    result = grader.grade(workspace, "challenge-03-seed-7-oracle")

    assert result.status.value == "PASSED"
    assert {metric.name for metric in result.metrics} >= {
        "performance_gain",
        "candidate_seconds",
        "baseline_seconds",
        "hidden_seed",
    }
    assert next(metric.value for metric in result.metrics if metric.name == "hidden_seed") == 7


def test_security_and_rollback_failures_keep_their_own_dimensions(tmp_path: Path) -> None:
    project_root = Path(__file__).parents[2]
    outcomes = {}
    for challenge_id in ("04_adversarial_security", "05_containment_rollback"):
        challenge_root = project_root / "challenges" / challenge_id
        workspace = tmp_path / challenge_id
        shutil.copytree(
            challenge_root / "fixture",
            workspace,
            ignore=shutil.ignore_patterns("controls", "__pycache__", "*.pyc"),
        )
        outcomes[challenge_id] = _pytest_grader_factory(challenge_root / "grader")().grade(
            workspace, challenge_id
        )

    assert outcomes["04_adversarial_security"].status.value == "SAFETY_FAIL"
    assert outcomes["04_adversarial_security"].safety == "FAIL"
    assert outcomes["05_containment_rollback"].rollback == "FAIL"
