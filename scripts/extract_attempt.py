"""Safely extract a single frozen attempt from an artifact archive."""

from __future__ import annotations

import argparse
from pathlib import Path, PurePosixPath
import tarfile


def extract_attempt(archive: Path, destination: Path) -> Path:
    archive = archive.resolve()
    destination = destination.resolve()
    destination.mkdir(parents=True, exist_ok=True)

    with tarfile.open(archive, "r:gz") as stream:
        members = stream.getmembers()
        if not members:
            raise ValueError("attempt archive is empty")
        roots: set[str] = set()
        for member in members:
            path = PurePosixPath(member.name)
            if path.is_absolute() or ".." in path.parts or not path.parts:
                raise ValueError(f"unsafe archive path: {member.name}")
            if member.issym() or member.islnk() or member.isdev():
                raise ValueError(f"links and device entries are forbidden: {member.name}")
            roots.add(path.parts[0])
        if len(roots) != 1:
            raise ValueError("attempt archive must contain exactly one run directory")
        root_name = next(iter(roots))
        run_dir = destination / root_name
        if run_dir.exists():
            raise ValueError(f"run directory already exists: {root_name}")
        # Paths and entry types were fully validated above; preserving modes is
        # required because after.sha256 intentionally binds file permissions.
        stream.extractall(destination, filter="fully_trusted")

    if not (run_dir / "manifest.json").is_file():
        raise ValueError("attempt archive is missing manifest.json")
    return run_dir


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("archive", type=Path)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args(argv)
    print(extract_attempt(args.archive, args.destination))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
