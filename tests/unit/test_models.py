"""Contract tests for persisted MEA-EB5 foundation models."""

from __future__ import annotations

import json
from pathlib import Path
import tomllib

import jsonschema
import pytest

from mea_eb5.models import (
    EvidenceClass,
    Manifest,
    Metric,
    RunConfig,
    RunResult,
    RunStatus,
    Score,
)


SCHEMAS = Path(__file__).parents[2] / "schemas"
SHA256 = "a" * 64
REQUIRED_ATTEMPT_ARTIFACTS = {
    "raw-terminal.log",
    "events.jsonl",
    "resource-usage.csv",
    "before.sha256",
    "after.sha256",
    "changes.patch",
    "public.junit.xml",
    "hidden.junit.xml",
    "score.json",
    "manifest.json",
}


def test_run_config_rejects_zero_seed_count() -> None:
    """A non-positive seed count would make a published run unreproducible."""
    with pytest.raises(ValueError, match="seeds"):
        RunConfig(challenge_id="01", adapter="noop", seeds=0, timeout_seconds=60)


def test_run_config_rejects_non_positive_timeout() -> None:
    """A run with no time budget cannot be a meaningful benchmark attempt."""
    with pytest.raises(ValueError, match="timeout_seconds"):
        RunConfig(challenge_id="01", adapter="noop", seeds=1, timeout_seconds=0)


def test_statuses_keep_infrastructure_separate() -> None:
    """Infrastructure failure must remain distinguishable from agent failure."""
    assert RunStatus.INFRA_FAILURE != RunStatus.FUNCTIONAL_FAIL
    assert EvidenceClass.REAL.value == "REAL"


def test_run_result_serializes_enum_values_and_artifact_hashes() -> None:
    """Persisted results retain auditable identifiers rather than Enum objects."""
    result = RunResult(
        schema_version="1.0",
        run_id="run-001",
        status=RunStatus.FUNCTIONAL_FAIL,
        started_at="2026-08-27T12:00:00Z",
        finished_at="2026-08-27T12:01:00Z",
        config=RunConfig(challenge_id="01", adapter="noop"),
        artifact_hashes={"events.jsonl": SHA256},
        contributing_failures=(RunStatus.FUNCTIONAL_FAIL,),
    )

    assert result.to_dict() == {
        "schema_version": "1.0",
        "run_id": "run-001",
        "status": "FUNCTIONAL_FAIL",
        "started_at": "2026-08-27T12:00:00Z",
        "finished_at": "2026-08-27T12:01:00Z",
        "config": {
            "challenge_id": "01",
            "adapter": "noop",
            "seeds": 5,
            "timeout_seconds": 900,
        },
        "artifact_hashes": {"events.jsonl": SHA256},
        "contributing_failures": ["FUNCTIONAL_FAIL"],
        "error_message": None,
    }


def test_score_keeps_metric_units_and_validates_its_schema() -> None:
    """A metric without units could support misleading performance claims."""
    score = Score(
        schema_version="1.0",
        run_id="run-001",
        status=RunStatus.PASSED,
        generated_at="2026-08-27T12:01:00Z",
        functional_score=100.0,
        evidence_class=EvidenceClass.REAL,
        safety="PASS",
        integrity="PASS",
        rollback="NOT_APPLICABLE",
        metrics=(Metric(name="clean_successes", value=1.0, unit="count"),),
        artifact_hashes={"score-input.json": SHA256},
        grader_id="hidden-grader@sha256:" + SHA256,
        grader_provenance="INDEPENDENT",
    )

    payload = score.to_dict()
    assert payload["metrics"] == [
        {"name": "clean_successes", "value": 1.0, "unit": "count"}
    ]
    assert payload["grader_id"] == "hidden-grader@sha256:" + SHA256
    assert payload["grader_provenance"] == "INDEPENDENT"
    _validate("score.schema.json", payload)


def test_real_score_rejects_self_reported_grader() -> None:
    """Self-reported evidence cannot be promoted to REAL evidence."""
    with pytest.raises(ValueError, match="independent"):
        Score(
            schema_version="1.0",
            run_id="run-001",
            status=RunStatus.PASSED,
            generated_at="2026-08-27T12:01:00Z",
            functional_score=100.0,
            evidence_class=EvidenceClass.REAL,
            safety="PASS",
            integrity="PASS",
            rollback="NOT_APPLICABLE",
            metrics=(Metric(name="clean_successes", value=1.0, unit="count"),),
            artifact_hashes={"score-input.json": SHA256},
            grader_id="agent-self-report",
            grader_provenance="SELF_REPORTED",
        )


def test_score_schema_rejects_real_evidence_without_independent_grader() -> None:
    """Persisted REAL evidence must retain independent grader provenance."""
    payload = Score(
        schema_version="1.0",
        run_id="run-001",
        status=RunStatus.PASSED,
        generated_at="2026-08-27T12:01:00Z",
        functional_score=100.0,
        evidence_class=EvidenceClass.REAL,
        safety="PASS",
        integrity="PASS",
        rollback="NOT_APPLICABLE",
        metrics=(Metric(name="clean_successes", value=1.0, unit="count"),),
        artifact_hashes={"score-input.json": SHA256},
        grader_id="hidden-grader@sha256:" + SHA256,
        grader_provenance="INDEPENDENT",
    ).to_dict()
    payload["grader_provenance"] = "SELF_REPORTED"

    with pytest.raises(jsonschema.ValidationError):
        _validate("score.schema.json", payload)


def test_manifest_requires_hashes_and_validates_a_complete_run() -> None:
    """A manifest lacking artifact hashes cannot reproduce or audit a run."""
    manifest = Manifest(
        schema_version="1.0",
        run_id="run-001",
        status=RunStatus.PASSED,
        started_at="2026-08-27T12:00:00Z",
        finished_at="2026-08-27T12:01:00Z",
        seed=17,
        config=RunConfig(challenge_id="01", adapter="noop", seeds=1),
        artifact_hashes=_required_artifact_hashes(),
        git_commit="b" * 40,
        images={"fixture": f"sha256:{SHA256}"},
        adapter_version="1.0.0",
        versions={"python": "3.12.0", "mea-eb5": "0.1.0"},
        network_allowed=False,
    )

    payload = manifest.to_dict()
    _validate("manifest.schema.json", payload)
    payload["unexpected"] = True
    with pytest.raises(jsonschema.ValidationError):
        _validate("manifest.schema.json", payload)


def test_manifest_rejects_missing_required_attempt_artifact() -> None:
    """A missing mandatory artifact would make an attempt unauditable."""
    artifact_hashes = _required_artifact_hashes()
    del artifact_hashes["hidden.junit.xml"]

    with pytest.raises(ValueError, match="hidden.junit.xml"):
        _make_manifest(artifact_hashes)


def test_manifest_schema_rejects_missing_required_attempt_artifact() -> None:
    """Schema validation must also reject manifests missing a required artifact."""
    payload = _make_manifest(_required_artifact_hashes()).to_dict()
    del payload["artifact_hashes"]["public.junit.xml"]

    with pytest.raises(jsonschema.ValidationError):
        _validate("manifest.schema.json", payload)


def test_package_publishes_the_implemented_cli_entrypoint() -> None:
    """Installing the benchmark must expose its validated console command."""
    project = tomllib.loads((Path(__file__).parents[2] / "pyproject.toml").read_text())
    assert project["project"]["scripts"]["mea-eb5"] == "mea_eb5.cli:main"


def test_event_schema_requires_run_identity_timestamp_and_hash_chain() -> None:
    """An event missing its identity or hash fields cannot join an audit trail."""
    payload = {
        "schema_version": "1.0",
        "run_id": "run-001",
        "sequence": 1,
        "timestamp": "2026-08-27T12:00:00Z",
        "monotonic_ns": 123,
        "source": "collector",
        "type": "run_started",
        "payload": {"adapter": "noop"},
        "task_id": None,
        "parent_run_id": None,
        "provenance": "collector",
        "sensitivity": "PUBLIC",
        "previous_hash": None,
        "event_hash": SHA256,
    }

    _validate("event.schema.json", payload)
    del payload["timestamp"]
    with pytest.raises(jsonschema.ValidationError):
        _validate("event.schema.json", payload)


def _validate(schema_name: str, instance: object) -> None:
    schema = json.loads((SCHEMAS / schema_name).read_text(encoding="utf-8"))
    jsonschema.validate(instance=instance, schema=schema, format_checker=jsonschema.Draft202012Validator.FORMAT_CHECKER)


def _required_artifact_hashes() -> dict[str, str]:
    return {name: SHA256 for name in REQUIRED_ATTEMPT_ARTIFACTS}


def _make_manifest(artifact_hashes: dict[str, str]) -> Manifest:
    return Manifest(
        schema_version="1.0",
        run_id="run-001",
        status=RunStatus.PASSED,
        started_at="2026-08-27T12:00:00Z",
        finished_at="2026-08-27T12:01:00Z",
        seed=17,
        config=RunConfig(challenge_id="01", adapter="noop", seeds=1),
        artifact_hashes=artifact_hashes,
        git_commit="b" * 40,
        images={"fixture": f"sha256:{SHA256}"},
        adapter_version="1.0.0",
        versions={"python": "3.12.0", "mea-eb5": "0.1.0"},
        network_allowed=False,
    )
