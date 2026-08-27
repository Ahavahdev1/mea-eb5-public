"""Contract tests for untrusted-agent adapters."""

from __future__ import annotations

import json
from pathlib import Path
import sys
import threading
import time
from urllib.error import HTTPError

import pytest

from mea_eb5.adapters import CliAdapter, HttpRepairAdapter, NoopAdapter, TaskRequest
from mea_eb5.events import EventSink
from mea_eb5.adapter_config import load_adapter
from mea_eb5.adapters.container import ContainerCliAdapter


def _task() -> TaskRequest:
    return TaskRequest(
        task_id="repair-001",
        filename="src/example.py",
        code="def answer():\n    return 0\n",
        instruction="Return 42; $(touch SHOULD_NOT_RUN)",
    )


def test_noop_control_performs_no_workspace_or_event_writes(tmp_path: Path) -> None:
    """A no-op control must not create evidence that resembles agent activity."""
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    sink = EventSink(workspace / "events.jsonl", "run-1")

    result = NoopAdapter().run(_task(), workspace, sink)

    assert result.succeeded is True
    assert list(workspace.iterdir()) == []


def test_cli_passes_goal_as_workspace_file_not_shell_text(tmp_path: Path) -> None:
    """Shell-like task text must reach a CLI only through a goal-file argument."""
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    argv_path = workspace / "argv.json"
    command = [
        sys.executable,
        "-c",
        "import json, pathlib, sys; pathlib.Path(sys.argv[1]).write_text(json.dumps(sys.argv[2:]))",
        str(argv_path),
    ]

    result = CliAdapter(command, timeout_seconds=2).run(
        _task(), workspace, EventSink(tmp_path / "events.jsonl", "run-1")
    )

    argv = json.loads(argv_path.read_text(encoding="utf-8"))
    assert result.succeeded is True
    assert "$(touch SHOULD_NOT_RUN)" not in argv
    assert argv[-2] == "--goal-file"
    goal_file = Path(argv[-1])
    assert goal_file.parent == workspace
    assert goal_file.read_text(encoding="utf-8") == _task().instruction
    assert (workspace / "raw-terminal.log").exists()


def test_cli_timeout_terminates_its_entire_process_group(tmp_path: Path) -> None:
    """A timed-out CLI must not leave a child process writing after the run ends."""
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    child_marker = workspace / "child-survived"
    child_code = (
        "import pathlib, sys, time; "
        "time.sleep(0.8); pathlib.Path(sys.argv[1]).write_text('survived')"
    )
    parent_code = (
        "import subprocess, sys, time; "
        "subprocess.Popen([sys.executable, '-c', sys.argv[1], sys.argv[2]]); time.sleep(10)"
    )

    result = CliAdapter(
        [sys.executable, "-c", parent_code, child_code, str(child_marker)], timeout_seconds=0.1
    ).run(_task(), workspace, EventSink(tmp_path / "events.jsonl", "run-1"))

    time.sleep(1.0)
    assert result.succeeded is False
    assert result.timed_out is True
    assert not child_marker.exists()
    assert (workspace / "raw-terminal.log").exists()


def test_cli_cancel_terminates_a_running_process(tmp_path: Path) -> None:
    """An explicit cancel() from the runner must kill the adapter process."""
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    marker = workspace / "never-written"
    adapter = CliAdapter(
        [sys.executable, "-c", "import time; time.sleep(30)"],
        timeout_seconds=30,
    )

    def cancel_after_start() -> None:
        # Wait until Popen has been assigned; polling avoids a race.
        while adapter._process is None:
            time.sleep(0.01)
        adapter.cancel("runner requested freeze")

    threading.Thread(target=cancel_after_start, daemon=True).start()
    result = adapter.run(_task(), workspace, EventSink(tmp_path / "events.jsonl", "run-1"))

    assert result.succeeded is False
    assert not marker.exists()
    assert (workspace / "raw-terminal.log").exists()


@pytest.mark.parametrize(
    "endpoint",
    ["http://repair.example.test", "ftp://localhost/repair", "https://"],
)
def test_http_rejects_endpoints_that_are_not_https_or_localhost(endpoint: str) -> None:
    """Remote repair requests must not send source code over insecure endpoints."""
    with pytest.raises(ValueError, match="HTTPS|localhost"):
        HttpRepairAdapter(endpoint)


def test_http_localhost_is_allowed_but_other_http_hosts_are_not() -> None:
    """A local test server is the sole permitted HTTP exception."""
    assert HttpRepairAdapter("http://localhost:8080/repair").describe().name == "http-repair"


def test_http_uses_env_auth_and_emits_no_credentials(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Authorization can reach the request header but never the body or event trail."""
    captured: dict[str, object] = {}

    class Response:
        status = 200

        def read(self, size: int = -1) -> bytes:
            return b'{"accepted":true}'

        def __enter__(self) -> Response:
            return self

        def __exit__(self, *_: object) -> None:
            return None

    def urlopen(request: object, *, timeout: float) -> Response:
        captured["request"] = request
        captured["timeout"] = timeout
        return Response()

    monkeypatch.setenv("MEASURE_AUTH", "Bearer private-value")
    monkeypatch.setattr("mea_eb5.adapters.http.urlopen", urlopen)
    event_path = tmp_path / "events.jsonl"
    result = HttpRepairAdapter(
        "https://repair.example.test/submit", auth_env="MEASURE_AUTH", timeout_seconds=3
    ).run(_task(), tmp_path / "workspace", EventSink(event_path, "run-1"))

    request = captured["request"]
    assert result.succeeded is True
    assert captured["timeout"] == 3
    assert request.get_header("Authorization") == "Bearer private-value"  # type: ignore[union-attr]
    assert json.loads(request.data) == {  # type: ignore[union-attr]
        "filename": "src/example.py",
        "code": "def answer():\n    return 0\n",
        "instruction": "Return 42; $(touch SHOULD_NOT_RUN)",
        "test_cmd": None,
    }
    assert "private-value" not in event_path.read_text(encoding="utf-8")


def test_http_protocol_errors_remain_failures(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """An HTTP protocol error must remain visible as an adapter failure."""
    def urlopen(*_: object, **__: object) -> object:
        raise HTTPError("https://repair.example.test", 503, "unavailable", {}, None)

    monkeypatch.setattr("mea_eb5.adapters.http.urlopen", urlopen)
    result = HttpRepairAdapter("https://repair.example.test", timeout_seconds=1).run(
        _task(), tmp_path / "workspace", EventSink(tmp_path / "events.jsonl", "run-1")
    )

    assert result.succeeded is False
    assert result.error_kind == "protocol_error"


def test_http_rejects_responses_larger_than_ten_mebibytes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An overlarge remote response must not exhaust benchmark memory."""
    class Response:
        status = 200

        def read(self, size: int = -1) -> bytes:
            return b"x" * (10 * 1024 * 1024 + 1)

        def __enter__(self) -> Response:
            return self

        def __exit__(self, *_: object) -> None:
            return None

    monkeypatch.setattr("mea_eb5.adapters.http.urlopen", lambda *_args, **_kwargs: Response())
    result = HttpRepairAdapter("https://repair.example.test", timeout_seconds=1).run(
        _task(), tmp_path / "workspace", EventSink(tmp_path / "events.jsonl", "run-1")
    )

    assert result.succeeded is False
    assert result.error_kind == "response_too_large"


def test_adapter_config_rejects_implicit_host_execution(tmp_path: Path) -> None:
    """A production CLI config must not silently execute the MEA on the host."""
    config = tmp_path / "adapter.yaml"
    config.write_text("kind: cli\ncommand: [mea, run]\n", encoding="utf-8")
    with pytest.raises(ValueError, match="image|host execution"):
        load_adapter(config, timeout_seconds=60)


def test_adapter_config_builds_digest_pinned_container_command(tmp_path: Path) -> None:
    """The official CLI path must mount only the workspace into a pinned image."""
    config = tmp_path / "adapter.yaml"
    image = "mea@sha256:" + "a" * 64
    config.write_text(
        "kind: cli\n"
        f"image: {image}\n"
        "command: [mea, run]\n"
        "cpu: 2\n"
        "memory: 2g\n"
        "pids: 128\n",
        encoding="utf-8",
    )
    adapter = load_adapter(config, timeout_seconds=60)
    assert isinstance(adapter, ContainerCliAdapter)
    argv = adapter.build_argv(tmp_path / "workspace")
    assert argv[-5:] == [
        image,
        "mea",
        "run",
        "--goal-file",
        "/workspace/.mea-eb5-goal.txt",
    ]
    assert "/var/run/docker.sock" not in " ".join(argv)
    assert "--network none" in " ".join(argv)
