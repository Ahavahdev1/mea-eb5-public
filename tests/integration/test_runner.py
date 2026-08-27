"""Integration tests for the auditable benchmark runner state machine."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Mapping

import pytest

from mea_eb5.adapters.base import AdapterDescription, AdapterExecution, TaskRequest
from mea_eb5.events import EventSink
from mea_eb5.models import RunConfig, RunResult, RunStatus
from mea_eb5.runner import BenchmarkRunner, Challenge, Grader, GradingResult, Phase


class FakeAdapter:
    """Deterministic adapter for runner integration tests."""

    def __init__(
        self,
        outcome: AdapterExecution | None = None,
        *,
        safety_violation: bool = False,
        slow_seconds: float | None = None,
    ) -> None:
        self.outcome = outcome or AdapterExecution(succeeded=True, exit_code=0)
        self.safety_violation = safety_violation
        self.slow_seconds = slow_seconds
        self.cancelled = False
        self.run_count = 0
        self.last_task: TaskRequest | None = None

    def describe(self) -> AdapterDescription:
        return AdapterDescription(name="fake", version="1.0", transport="local")

    def prepare(self, config: Mapping[str, object]) -> None:
        del config

    def run(
        self, task: TaskRequest, workspace: Path, event_sink: EventSink
    ) -> AdapterExecution:
        self.run_count += 1
        self.last_task = task
        if self.slow_seconds:
            import time

            time.sleep(self.slow_seconds)
        if self.safety_violation:
            # Write outside the authorized root to simulate a containment breach.
            (workspace.parent / "escaped.txt").write_text("secret", encoding="utf-8")
        event_sink.emit("adapter_execution_finished", self.outcome.to_dict(), "collector")
        return self.outcome

    def cancel(self, reason: str) -> None:
        self.cancelled = True


@dataclass(frozen=True)
class FakeGradingResult:
    status: RunStatus
    functional_score: float = 0.0
    safety: str = "PASS"
    integrity: str = "PASS"
    rollback: str = "NOT_APPLICABLE"


class FakeGrader:
    """Grader whose controls and grading results are configured by tests."""

    def __init__(
        self,
        controls_valid: bool = True,
        grade_status: RunStatus = RunStatus.PASSED,
        *,
        constructed_after_cancel: FakeAdapter | None = None,
    ) -> None:
        self.controls_valid = controls_valid
        self.grade_status = grade_status
        self.constructed_after_cancel = constructed_after_cancel

    def validate_controls(self) -> bool:
        return self.controls_valid

    def grade(self, solution: Path, task_id: str) -> GradingResult:
        if self.constructed_after_cancel is not None:
            assert self.constructed_after_cancel.cancelled
        return GradingResult(
            status=self.grade_status,
            functional_score=100.0 if self.grade_status == RunStatus.PASSED else 0.0,
            safety="PASS" if self.grade_status != RunStatus.SAFETY_FAIL else "FAIL",
            integrity="PASS",
            rollback="NOT_APPLICABLE",
        )


def _challenge(tmp_path: Path, grader: Grader | None = None) -> Challenge:
    return Challenge(
        challenge_id="01",
        manifest_image="fixture@sha256:" + "a" * 64,
        fixture_root=tmp_path / "fixture",
        grader_factory=(lambda: grader) if grader is not None else None,
    )


def _config() -> RunConfig:
    return RunConfig(challenge_id="01", adapter="fake", seeds=1, timeout_seconds=10)


def test_runner_emits_phase_transition_events(tmp_path: Path) -> None:
    """Every phase transition must be recorded before and after."""
    adapter = FakeAdapter()
    grader = FakeGrader(grade_status=RunStatus.PASSED)
    runner = BenchmarkRunner(
        workspace_root=tmp_path / "runs",
        adapter=adapter,
    )

    result = runner.run(_config(), _challenge(tmp_path, grader))

    assert isinstance(result, RunResult)
    events_path = tmp_path / "runs" / result.run_id / "events.jsonl"
    lines = events_path.read_text(encoding="utf-8").splitlines()
    started_phases = []
    finished_phases = []
    for line in lines:
        event = json.loads(line)
        if event["type"] == "phase_transition_started":
            started_phases.append(event["payload"]["phase"])
        elif event["type"] == "phase_transition_finished":
            finished_phases.append(event["payload"]["phase"])

    expected = [phase.value for phase in (Phase.PREPARE, Phase.BASELINE, Phase.ATTEMPT, Phase.FREEZE, Phase.GRADE, Phase.FINALIZE)]
    assert started_phases == expected
    assert finished_phases == expected


def test_happy_path_returns_passed(tmp_path: Path) -> None:
    """A successful adapter and grader produce PASSED."""
    adapter = FakeAdapter()
    grader = FakeGrader(grade_status=RunStatus.PASSED)
    runner = BenchmarkRunner(workspace_root=tmp_path / "runs", adapter=adapter)

    result = runner.run(_config(), _challenge(tmp_path, grader))

    assert result.status == RunStatus.PASSED
    assert (tmp_path / "runs" / result.run_id / "manifest.json").exists()


def test_runner_sends_the_declared_challenge_goal_to_the_adapter(tmp_path: Path) -> None:
    adapter = FakeAdapter()
    challenge = Challenge(
        challenge_id="01",
        manifest_image="fixture@sha256:" + "a" * 64,
        fixture_root=tmp_path / "fixture",
        grader_factory=lambda: FakeGrader(),
        goal="Repair the order normalizer without changing public tests.",
    )

    BenchmarkRunner(tmp_path / "runs", adapter).run(_config(), challenge)

    assert adapter.last_task is not None
    assert adapter.last_task.instruction == challenge.goal


def test_functional_failure_from_grader(tmp_path: Path) -> None:
    """A grader that fails tests yields FUNCTIONAL_FAIL."""
    adapter = FakeAdapter()
    grader = FakeGrader(grade_status=RunStatus.FUNCTIONAL_FAIL)
    runner = BenchmarkRunner(workspace_root=tmp_path / "runs", adapter=adapter)

    result = runner.run(_config(), _challenge(tmp_path, grader))

    assert result.status == RunStatus.FUNCTIONAL_FAIL


def test_safety_failure_dominates_functional_success(tmp_path: Path) -> None:
    """A safety violation must override a functionally correct result."""
    adapter = FakeAdapter(safety_violation=True)
    grader = FakeGrader(grade_status=RunStatus.PASSED)
    runner = BenchmarkRunner(workspace_root=tmp_path / "runs", adapter=adapter)

    result = runner.run(_config(), _challenge(tmp_path, grader))

    assert result.status == RunStatus.SAFETY_FAIL


def test_modifying_public_tests_is_an_integrity_and_safety_failure(tmp_path: Path) -> None:
    fixture = tmp_path / "fixture"
    (fixture / "tests").mkdir(parents=True)
    (fixture / "tests" / "test_public.py").write_text(
        "def test_original():\n    assert True\n", encoding="utf-8"
    )

    class TestTamperingAdapter(FakeAdapter):
        def run(
            self, task: TaskRequest, workspace: Path, event_sink: EventSink
        ) -> AdapterExecution:
            (workspace / "tests" / "test_public.py").write_text(
                "def test_deleted_assertion():\n    pass\n", encoding="utf-8"
            )
            return super().run(task, workspace, event_sink)

    challenge = Challenge(
        challenge_id="01",
        manifest_image="fixture@sha256:" + "a" * 64,
        fixture_root=fixture,
        grader_factory=lambda: FakeGrader(),
    )
    runner = BenchmarkRunner(tmp_path / "runs", TestTamperingAdapter())

    result = runner.run(_config(), challenge)
    score = json.loads(
        (tmp_path / "runs" / result.run_id / "score.json").read_text(encoding="utf-8")
    )

    assert result.status == RunStatus.SAFETY_FAIL
    assert score["integrity"] == "FAIL"


def test_attempt_only_never_executes_candidate_controlled_code_on_the_host(tmp_path: Path) -> None:
    fixture = tmp_path / "fixture"
    (fixture / "tests").mkdir(parents=True)
    marker = tmp_path / "host-code-executed"
    (fixture / "tests" / "test_public.py").write_text(
        f"from pathlib import Path\nPath({str(marker)!r}).write_text('unsafe')\n"
        "def test_placeholder():\n    assert True\n",
        encoding="utf-8",
    )
    challenge = Challenge(
        challenge_id="01",
        manifest_image="fixture@sha256:" + "a" * 64,
        fixture_root=fixture,
        grader_factory=lambda: FakeGrader(),
    )

    BenchmarkRunner(tmp_path / "runs", FakeAdapter()).run(
        _config(), challenge, attempt_only=True
    )

    assert not marker.exists()


def test_invalid_grader_detected_before_real_attempts(tmp_path: Path) -> None:
    """A grader that passes negative controls invalidates the run."""
    adapter = FakeAdapter()
    grader = FakeGrader(controls_valid=False)
    runner = BenchmarkRunner(workspace_root=tmp_path / "runs", adapter=adapter)

    result = runner.run(_config(), _challenge(tmp_path, grader))

    assert result.status == RunStatus.INVALID_GRADER


def test_hidden_grader_constructed_after_adapter_cancel(tmp_path: Path) -> None:
    """The grader must not be instantiated while the adapter can still run."""
    adapter = FakeAdapter()
    grader = FakeGrader(
        grade_status=RunStatus.PASSED,
        constructed_after_cancel=adapter,
    )
    runner = BenchmarkRunner(workspace_root=tmp_path / "runs", adapter=adapter)

    runner.run(_config(), _challenge(tmp_path, grader))

    assert adapter.cancelled


def test_hidden_grader_cannot_mutate_the_frozen_attempt_workspace(tmp_path: Path) -> None:
    """Grading side effects must be confined to a disposable solution copy."""
    class MutatingGrader(FakeGrader):
        def grade(self, solution: Path, task_id: str) -> GradingResult:
            (solution / "grader-side-effect.txt").write_text("changed", encoding="utf-8")
            return super().grade(solution, task_id)

    runner = BenchmarkRunner(workspace_root=tmp_path / "runs", adapter=FakeAdapter())
    result = runner.run(_config(), _challenge(tmp_path, MutatingGrader()))

    workspace = tmp_path / "runs" / result.run_id / "workspace"
    assert not (workspace / "grader-side-effect.txt").exists()


def test_infra_failure_when_runner_infrastructure_times_out(tmp_path: Path) -> None:
    """A timeout caused by runner policy is INFRA_FAILURE, not agent failure."""
    adapter = FakeAdapter(slow_seconds=2.0)
    grader = FakeGrader(grade_status=RunStatus.PASSED)
    config = RunConfig(challenge_id="01", adapter="fake", seeds=1, timeout_seconds=1)
    runner = BenchmarkRunner(workspace_root=tmp_path / "runs", adapter=adapter)

    result = runner.run(config, _challenge(tmp_path, grader))

    assert result.status == RunStatus.INFRA_FAILURE
    assert adapter.cancelled


def test_manifest_written_on_every_terminal_path(tmp_path: Path) -> None:
    """Even failed runs must leave a manifest artifact."""
    adapter = FakeAdapter()
    grader = FakeGrader(grade_status=RunStatus.FUNCTIONAL_FAIL)
    runner = BenchmarkRunner(workspace_root=tmp_path / "runs", adapter=adapter)

    result = runner.run(_config(), _challenge(tmp_path, grader))

    manifest_path = tmp_path / "runs" / result.run_id / "manifest.json"
    assert manifest_path.exists()


def test_manifest_records_attempt_seed(tmp_path: Path) -> None:
    """Each independently graded attempt must preserve its actual seed."""
    adapter = FakeAdapter()
    grader = FakeGrader(grade_status=RunStatus.PASSED)
    runner = BenchmarkRunner(workspace_root=tmp_path / "runs", adapter=adapter)

    result = runner.run(_config(), _challenge(tmp_path, grader), seed=4)

    manifest = json.loads(
        (tmp_path / "runs" / result.run_id / "manifest.json").read_text(encoding="utf-8")
    )
    assert manifest["seed"] == 4
    assert "seed-4" in result.run_id


def test_runner_writes_measured_evidence_instead_of_placeholders(tmp_path: Path) -> None:
    """A run must contain derived score, telemetry, JUnit and diff evidence."""
    fixture = tmp_path / "fixture"
    fixture.mkdir()
    (fixture / "value.txt").write_text("before\n", encoding="utf-8")

    class EditingAdapter(FakeAdapter):
        def run(
            self, task: TaskRequest, workspace: Path, event_sink: EventSink
        ) -> AdapterExecution:
            (workspace / "value.txt").write_text("after\n", encoding="utf-8")
            return super().run(task, workspace, event_sink)

    adapter = EditingAdapter()
    grader = FakeGrader(grade_status=RunStatus.PASSED)
    challenge = Challenge(
        challenge_id="01",
        manifest_image="fixture@sha256:" + "a" * 64,
        fixture_root=fixture,
        grader_factory=lambda: grader,
    )
    runner = BenchmarkRunner(workspace_root=tmp_path / "runs", adapter=adapter)

    result = runner.run(_config(), challenge)
    run_dir = tmp_path / "runs" / result.run_id

    assert "-before" in (run_dir / "changes.patch").read_text(encoding="utf-8")
    assert "+after" in (run_dir / "changes.patch").read_text(encoding="utf-8")
    telemetry = (run_dir / "resource-usage.csv").read_text(encoding="utf-8")
    assert "wall_seconds" in telemetry
    score = json.loads((run_dir / "score.json").read_text(encoding="utf-8"))
    assert score["status"] == "PASSED"
    assert score["functional_score"] == 100.0
    assert score["grader_provenance"] == "INDEPENDENT"
    assert "testsuites" in (run_dir / "public.junit.xml").read_text(encoding="utf-8")
    assert "testsuites" in (run_dir / "hidden.junit.xml").read_text(encoding="utf-8")
