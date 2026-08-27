"""Contract tests for the immutable container policy builder."""

from __future__ import annotations

from pathlib import Path

import pytest

from mea_eb5.isolation import ContainerSpec, docker_argv


SHA256 = "a" * 64


def _spec(**overrides: object) -> ContainerSpec:
    defaults = {
        "image": f"fixture@sha256:{SHA256}",
        "cpu": 1.0,
        "memory": "512m",
        "pids": 64,
        "workspace": Path("/tmp/workspace"),
        "timeout_seconds": 30,
    }
    defaults.update(overrides)
    return ContainerSpec(**defaults)  # type: ignore[arg-type]


def test_default_container_has_no_network_or_privileges() -> None:
    """The default argv must drop network and privilege escalation."""
    argv = docker_argv(_spec())
    joined = " ".join(argv)

    assert "--network none" in joined
    assert "--cap-drop ALL" in joined
    assert "no-new-privileges" in joined
    assert "/var/run/docker.sock" not in joined


def test_container_spec_rejects_images_without_digest() -> None:
    """Only digest-pinned images are reproducible."""
    with pytest.raises(ValueError, match="digest-pinned"):
        _spec(image="fixture:latest")


def test_docker_argv_includes_resource_limits() -> None:
    """CPU, memory, PIDs and timeout must be present as argv flags."""
    argv = docker_argv(_spec(cpu=2.0, memory="1g", pids=128, timeout_seconds=60))

    assert "--cpus" in argv
    assert "2.0" in argv
    assert "--memory" in argv
    assert "1g" in argv
    assert "--pids-limit" in argv
    assert "128" in argv
    assert "--stop-timeout" in argv
    assert "60" in argv


def test_docker_argv_mounts_workspace_writably() -> None:
    """The workspace must be bind-mounted so the container can write evidence."""
    workspace = Path("/tmp/ws")
    argv = docker_argv(_spec(workspace=workspace))

    mount = next(arg for arg in argv if arg.startswith("/tmp/ws:"))
    assert mount == "/tmp/ws:/workspace"
    # A writable mount has no explicit :ro suffix.
    assert not mount.endswith(":ro")


def test_docker_argv_runs_as_nobody() -> None:
    """Containers must execute as an unprivileged user."""
    argv = docker_argv(_spec())

    assert "--user" in argv
    assert argv[argv.index("--user") + 1] == "65534:65534"


def test_container_is_ephemeral_and_has_bounded_temporary_storage() -> None:
    argv = docker_argv(_spec())
    joined = " ".join(argv)

    assert "--rm" in argv
    assert "--init" in argv
    assert "--workdir /workspace" in joined
    assert "--tmpfs /tmp:rw,noexec,nosuid,size=64m" in joined


def test_docker_argv_adds_readonly_root_by_default() -> None:
    """The root filesystem is read-only unless explicitly relaxed."""
    assert "--read-only" in docker_argv(_spec())
    assert "--read-only" not in docker_argv(_spec(readonly_root=False))


def test_docker_argv_uses_custom_network_policy() -> None:
    """The network policy is surfaced verbatim on the command line."""
    argv = docker_argv(_spec(network="bridge"))

    assert "--network" in argv
    assert argv[argv.index("--network") + 1] == "bridge"


def test_container_spec_validates_positive_resources() -> None:
    """Zero or negative resource limits are rejected early."""
    with pytest.raises(ValueError, match="pids"):
        _spec(pids=0)
    with pytest.raises(ValueError, match="timeout_seconds"):
        _spec(timeout_seconds=-1)
    with pytest.raises(ValueError, match="cpu"):
        _spec(cpu=0)
