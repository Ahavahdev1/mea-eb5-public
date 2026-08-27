"""Contract tests for tamper-evident canonical event logs."""

from __future__ import annotations

import hashlib
import json

from mea_eb5.events import EventSink, verify_event_chain


def test_event_sink_redacts_recursively_and_chains(tmp_path) -> None:
    """Secrets must be absent from both emitted data and the persisted hash chain."""
    path = tmp_path / "events.jsonl"
    sink = EventSink(path, "run-1")

    first = sink.emit(
        "tool_call",
        {
            "authorization": "Bearer secret-value",
            "nested": [{"api_key": "another-secret"}],
        },
        "collector",
    )
    second = sink.emit("result", {"ok": True}, "grader")

    persisted = path.read_text(encoding="utf-8")
    assert "secret-value" not in persisted
    assert "another-secret" not in persisted
    assert first["payload"] == {
        "authorization": "[REDACTED]",
        "nested": [{"api_key": "[REDACTED]"}],
    }
    assert second["sequence"] == 2
    assert second["previous_hash"] == first["event_hash"]
    assert verify_event_chain(path).valid


def test_event_sink_writes_deterministic_compact_sorted_json(tmp_path) -> None:
    """Equivalent event data must have a stable canonical persisted representation."""
    path = tmp_path / "events.jsonl"
    EventSink(path, "run-1").emit("result", {"z": 1, "a": {"y": False, "b": None}}, "native")

    line = path.read_text(encoding="utf-8")
    event = json.loads(line)

    assert line == json.dumps(event, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n"


def test_modified_event_breaks_chain(tmp_path) -> None:
    """Changing a hashed event payload must make verification fail at that event."""
    path = tmp_path / "events.jsonl"
    sink = EventSink(path, "run-1")
    sink.emit("tool_call", {"command": "safe"}, "collector")
    sink.emit("result", {"ok": True}, "grader")

    path.write_text(path.read_text(encoding="utf-8").replace("safe", "evil"), encoding="utf-8")

    verification = verify_event_chain(path)
    assert not verification.valid
    assert verification.first_invalid_sequence == 1


def test_removed_or_reordered_event_breaks_chain(tmp_path) -> None:
    """Removal or reordering cannot preserve sequence and previous-hash continuity."""
    path = tmp_path / "events.jsonl"
    sink = EventSink(path, "run-1")
    sink.emit("one", {}, "native")
    sink.emit("two", {}, "collector")
    sink.emit("three", {}, "grader")
    lines = path.read_text(encoding="utf-8").splitlines()

    path.write_text("\n".join((lines[0], lines[2])) + "\n", encoding="utf-8")
    removed = verify_event_chain(path)
    assert not removed.valid
    assert removed.first_invalid_sequence == 3

    path.write_text("\n".join((lines[1], lines[0], lines[2])) + "\n", encoding="utf-8")
    reordered = verify_event_chain(path)
    assert not reordered.valid
    assert reordered.first_invalid_sequence == 2


def test_malformed_json_and_sequence_gap_break_chain(tmp_path) -> None:
    """A verifier must reject malformed lines and forged non-contiguous sequences."""
    malformed_path = tmp_path / "malformed.jsonl"
    EventSink(malformed_path, "run-1").emit("one", {}, "native")
    malformed_path.write_text(
        malformed_path.read_text(encoding="utf-8") + "not-json\n", encoding="utf-8"
    )
    malformed = verify_event_chain(malformed_path)
    assert not malformed.valid
    assert malformed.first_invalid_sequence is None

    path = tmp_path / "events.jsonl"
    sink = EventSink(path, "run-1")
    sink.emit("one", {}, "native")
    sink.emit("two", {}, "collector")
    lines = path.read_text(encoding="utf-8").splitlines()
    forged = json.loads(lines[1])
    forged["sequence"] = 3
    lines[1] = json.dumps(forged, sort_keys=True, separators=(",", ":"))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    gap = verify_event_chain(path)
    assert not gap.valid
    assert gap.first_invalid_sequence == 3


def test_rehashed_invalid_timestamp_breaks_strict_envelope_validation(tmp_path) -> None:
    """A forged hash cannot make an event with an invalid RFC3339 timestamp valid."""
    path = tmp_path / "events.jsonl"
    EventSink(path, "run-1").emit("one", {}, "native")
    event = json.loads(path.read_text(encoding="utf-8"))
    event["timestamp"] = "not-a-timestamp"
    event["event_hash"] = _hash_event(event)
    path.write_text(json.dumps(event, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")

    verification = verify_event_chain(path)
    assert not verification.valid
    assert verification.first_invalid_sequence == 1


def test_noncanonical_json_format_breaks_chain_verification(tmp_path) -> None:
    """Changing a line's formatting must not create a second valid serialization."""
    path = tmp_path / "events.jsonl"
    EventSink(path, "run-1").emit("one", {}, "native")
    event = json.loads(path.read_text(encoding="utf-8"))
    path.write_text(json.dumps(event, sort_keys=True) + "\n", encoding="utf-8")

    verification = verify_event_chain(path)
    assert not verification.valid
    assert verification.first_invalid_sequence == 1


def test_final_line_truncation_breaks_terminal_commitment(tmp_path) -> None:
    """A valid prefix cannot replace the terminal event committed by the sink."""
    path = tmp_path / "events.jsonl"
    sink = EventSink(path, "run-1")
    sink.emit("one", {}, "native")
    sink.emit("two", {}, "collector")
    lines = path.read_text(encoding="utf-8").splitlines()
    path.write_text(lines[0] + "\n", encoding="utf-8")

    assert not verify_event_chain(path).valid


def test_missing_terminal_commitment_breaks_nonempty_event_log(tmp_path) -> None:
    """A nonempty sink log without its external terminal commitment is invalid."""
    path = tmp_path / "events.jsonl"
    EventSink(path, "run-1").emit("one", {}, "native")
    _checkpoint_path(path).unlink(missing_ok=True)

    assert not verify_event_chain(path).valid


def test_malformed_terminal_commitment_breaks_event_log(tmp_path) -> None:
    """A malformed terminal checkpoint cannot be trusted to bind the log tail."""
    path = tmp_path / "events.jsonl"
    EventSink(path, "run-1").emit("one", {}, "native")
    _checkpoint_path(path).write_text("not-json", encoding="utf-8")

    assert not verify_event_chain(path).valid


def test_stale_terminal_commitment_breaks_event_log(tmp_path) -> None:
    """A checkpoint must name the actual final sequence, count, and hash."""
    path = tmp_path / "events.jsonl"
    EventSink(path, "run-1").emit("one", {}, "native")
    event = json.loads(path.read_text(encoding="utf-8"))
    _checkpoint_path(path).write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "run_id": "run-1",
                "event_count": 2,
                "final_sequence": 2,
                "terminal_hash": event["event_hash"],
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n",
        encoding="utf-8",
    )

    assert not verify_event_chain(path).valid


def test_rehashed_plaintext_sensitive_payload_breaks_verification(tmp_path) -> None:
    """A matching hash and checkpoint cannot authorize plaintext sensitive values."""
    path = tmp_path / "events.jsonl"
    EventSink(path, "run-1").emit("one", {}, "native")
    event = json.loads(path.read_text(encoding="utf-8"))
    event["payload"] = {"token": "plaintext-secret"}
    event["sensitivity"] = "REDACTED"
    event["event_hash"] = _hash_event(event)
    path.write_text(json.dumps(event, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")
    _checkpoint_path(path).write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "run_id": "run-1",
                "event_count": 1,
                "final_sequence": 1,
                "terminal_hash": event["event_hash"],
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n",
        encoding="utf-8",
    )

    assert not verify_event_chain(path).valid


def test_empty_event_file_with_existing_terminal_commitment_is_invalid(tmp_path) -> None:
    """Truncating every event cannot bypass the sink's terminal commitment."""
    path = tmp_path / "events.jsonl"
    EventSink(path, "run-1").emit("one", {}, "native")
    path.write_text("", encoding="utf-8")

    assert not verify_event_chain(path).valid


def test_fresh_empty_event_file_without_terminal_commitment_is_valid(tmp_path) -> None:
    """A genuinely fresh empty log remains a valid starting state."""
    path = tmp_path / "events.jsonl"
    path.write_text("", encoding="utf-8")

    verification = verify_event_chain(path)
    assert verification.valid
    assert verification.event_count == 0


def _hash_event(event: dict[str, object]) -> str:
    unhashed = {key: value for key, value in event.items() if key != "event_hash"}
    serialized = json.dumps(unhashed, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _checkpoint_path(path):
    return path.with_name(path.name + ".checkpoint.json")
