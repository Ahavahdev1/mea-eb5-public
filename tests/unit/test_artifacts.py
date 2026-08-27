"""Contract tests for artifact integrity helpers."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from mea_eb5.artifacts import build_manifest, hash_tree, write_patch
from mea_eb5.models import REQUIRED_ATTEMPT_ARTIFACT_KEYS, Manifest, RunConfig, RunStatus


def _file_digest(rel_path: str, mode: int, data: bytes) -> str:
    payload = f"{rel_path}\0{mode}\0".encode() + data
    return hashlib.sha256(payload).hexdigest()


def test_hash_tree_is_deterministic_and_sorted(tmp_path: Path) -> None:
    """Equivalent trees must produce identical, lexicographically sorted hashes."""
    (tmp_path / "b.txt").write_text("b")
    (tmp_path / "a.txt").write_text("a")

    first = hash_tree(tmp_path)
    second = hash_tree(tmp_path)

    assert list(first.keys()) == ["a.txt", "b.txt"]
    assert first == second


def test_hash_tree_excludes_git_and_runs_directories(tmp_path: Path) -> None:
    """``.git`` and ``runs`` directories must never be part of the integrity tree."""
    (tmp_path / ".git").mkdir(parents=True)
    (tmp_path / ".git" / "HEAD").write_text("ref: main\n")
    (tmp_path / "runs").mkdir(parents=True)
    (tmp_path / "runs" / "latest").write_text("log\n")
    (tmp_path / "src").mkdir(parents=True)
    (tmp_path / "src" / "keep.py").write_text("x = 1\n")

    tree = hash_tree(tmp_path)

    assert set(tree) == {"src/keep.py"}


def test_hash_tree_hashes_relative_path_mode_and_bytes(tmp_path: Path) -> None:
    """The digest must bind the path, mode, and content together."""
    path = tmp_path / "file.txt"
    path.write_text("hello")
    mode = path.stat().st_mode

    expected = _file_digest("file.txt", mode, b"hello")
    assert hash_tree(tmp_path)["file.txt"] == expected


def test_hash_tree_rejects_symlink_escaping_workspace(tmp_path: Path) -> None:
    """A symlink pointing outside the hashed tree is a policy violation."""
    outside = tmp_path / "outside.txt"
    outside.write_text("secret")
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "link.txt").symlink_to(outside)

    with pytest.raises(ValueError, match="symlink escapes workspace"):
        hash_tree(workspace)


def test_hash_tree_follows_internal_file_symlink(tmp_path: Path) -> None:
    """A symlink that stays inside the workspace may contribute to the tree."""
    target = tmp_path / "target.txt"
    target.write_text("shared")
    (tmp_path / "link.txt").symlink_to(target)

    tree = hash_tree(tmp_path)

    assert "target.txt" in tree
    assert "link.txt" in tree
    # Both paths hash the same bytes but have different relative paths.
    assert tree["target.txt"] != tree["link.txt"]


def test_write_patch_detects_added_and_deleted_text_files(tmp_path: Path) -> None:
    """Text file additions and deletions appear as a unified diff."""
    before_root = tmp_path / "before"
    after_root = tmp_path / "after"
    before_root.mkdir()
    after_root.mkdir()
    (before_root / "old.txt").write_text("old line\n")
    (after_root / "new.txt").write_text("new line\n")

    before = hash_tree(before_root)
    after = hash_tree(after_root)
    patch = tmp_path / "changes.patch"

    write_patch(before, after, patch, before_root=before_root, after_root=after_root)

    text = patch.read_text(encoding="utf-8")
    assert "--- a/old.txt" in text
    assert "-old line" in text
    assert "+++ b/new.txt" in text
    assert "+new line" in text


def test_write_patch_records_binary_files_by_hash_transition(tmp_path: Path) -> None:
    """Binary changes must be recorded by hash, never diffed as text."""
    before_root = tmp_path / "before"
    after_root = tmp_path / "after"
    before_root.mkdir()
    after_root.mkdir()
    (before_root / "data.bin").write_bytes(b"\x00\x01")
    (after_root / "data.bin").write_bytes(b"\x00\x02")

    before = hash_tree(before_root)
    after = hash_tree(after_root)
    patch = tmp_path / "changes.patch"

    write_patch(before, after, patch, before_root=before_root, after_root=after_root)

    text = patch.read_text(encoding="utf-8")
    assert "Binary file data.bin changed" in text
    assert "->" in text
    assert "@@" not in text


def test_build_manifest_returns_required_provenance(tmp_path: Path) -> None:
    """A manifest must carry the image, commit, adapter, seed and network policy."""
    artifact_hashes = {name: "a" * 64 for name in REQUIRED_ATTEMPT_ARTIFACT_KEYS}

    manifest = build_manifest(
        run_id="run-004",
        status=RunStatus.PASSED,
        started_at="2026-08-27T12:00:00Z",
        finished_at="2026-08-27T12:01:00Z",
        seed=42,
        config=RunConfig(challenge_id="04", adapter="cli", seeds=1),
        artifact_hashes=artifact_hashes,
        git_commit="b" * 40,
        image_digest="sha256:" + "c" * 64,
        adapter_version="1.2.3",
        versions={"python": "3.12.0", "mea-eb5": "0.1.0"},
        network_allowed=False,
    )

    assert isinstance(manifest, Manifest)
    assert manifest.git_commit == "b" * 40
    assert manifest.images == {"benchmark": "sha256:" + "c" * 64}
    assert manifest.adapter_version == "1.2.3"
    assert manifest.seed == 42
    assert manifest.network_allowed is False
    assert manifest.artifact_hashes == artifact_hashes


def test_build_manifest_rejects_malformed_image_digest() -> None:
    """Only sha256 digests in the canonical form are permitted."""
    with pytest.raises(ValueError, match="image_digest"):
        build_manifest(
            run_id="run-004",
            status=RunStatus.PASSED,
            started_at="2026-08-27T12:00:00Z",
            finished_at="2026-08-27T12:01:00Z",
            seed=1,
            config=RunConfig(challenge_id="04", adapter="cli", seeds=1),
            artifact_hashes={name: "a" * 64 for name in REQUIRED_ATTEMPT_ARTIFACT_KEYS},
            git_commit="b" * 40,
            image_digest="not-a-digest",
            adapter_version="1.0.0",
        )
