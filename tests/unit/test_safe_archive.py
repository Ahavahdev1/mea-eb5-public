"""Security tests for cross-repository attempt archives."""

from io import BytesIO
from pathlib import Path
import tarfile

import pytest

from scripts.extract_attempt import extract_attempt


def test_extract_attempt_rejects_path_traversal(tmp_path: Path) -> None:
    archive = tmp_path / "bad.tar.gz"
    with tarfile.open(archive, "w:gz") as stream:
        info = tarfile.TarInfo("../escaped.txt")
        payload = b"escaped"
        info.size = len(payload)
        stream.addfile(info, BytesIO(payload))

    with pytest.raises((ValueError, tarfile.TarError)):
        extract_attempt(archive, tmp_path / "runs")
    assert not (tmp_path / "escaped.txt").exists()


def test_extract_attempt_requires_one_run_with_manifest(tmp_path: Path) -> None:
    source = tmp_path / "source" / "run-001"
    source.mkdir(parents=True)
    (source / "manifest.json").write_text("{}", encoding="utf-8")
    archive = tmp_path / "valid.tar.gz"
    with tarfile.open(archive, "w:gz") as stream:
        stream.add(source, arcname="run-001")

    run_dir = extract_attempt(archive, tmp_path / "runs")

    assert run_dir == tmp_path / "runs" / "run-001"
    assert (run_dir / "manifest.json").is_file()
