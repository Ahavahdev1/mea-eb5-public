"""Export the public runner repository without private evaluation material."""

from __future__ import annotations

import argparse
from pathlib import Path
import shutil

import yaml


_IGNORED_FIXTURE_NAMES = shutil.ignore_patterns("controls", "__pycache__", "*.pyc")


def export_participant_repo(source: Path, destination: Path) -> Path:
    """Create the exact repository tree that may be shared with the MEA engineer."""
    source = source.resolve()
    destination = destination.resolve()
    if destination.exists() and any(destination.iterdir()):
        raise ValueError(f"destination must be absent or empty: {destination}")
    destination.mkdir(parents=True, exist_ok=True)

    for name in (".gitignore", "pyproject.toml", "uv.lock", "mea.adapter.example.yaml"):
        shutil.copy2(source / name, destination / name)
    shutil.copy2(source / "docs" / "participant-readme.md", destination / "readme.md")
    shutil.copytree(
        source / "src",
        destination / "src",
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.egg-info"),
    )
    shutil.copytree(source / "schemas", destination / "schemas")
    public_scripts = destination / "scripts"
    public_scripts.mkdir()
    shutil.copy2(source / "scripts" / "run_attempt_job.sh", public_scripts)

    public_workflows = destination / ".github" / "workflows"
    public_workflows.mkdir(parents=True)
    shutil.copy2(
        source / ".github" / "workflows" / "benchmark.yml",
        public_workflows / "benchmark.yml",
    )

    challenge_destination = destination / "challenges"
    challenge_destination.mkdir()
    for challenge_root in sorted((source / "challenges").iterdir()):
        if not challenge_root.is_dir():
            continue
        exported_challenge = challenge_destination / challenge_root.name
        exported_challenge.mkdir()
        data = yaml.safe_load((challenge_root / "challenge.yaml").read_text(encoding="utf-8"))
        data.pop("grader_root", None)
        (exported_challenge / "challenge.yaml").write_text(
            yaml.safe_dump(data, sort_keys=False, allow_unicode=True),
            encoding="utf-8",
        )
        shutil.copytree(
            challenge_root / data.get("fixture_root", "fixture"),
            exported_challenge / data.get("fixture_root", "fixture"),
            ignore=_IGNORED_FIXTURE_NAMES,
        )

    return destination


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("destination", type=Path)
    parser.add_argument("--source", type=Path, default=Path(__file__).parents[1])
    args = parser.parse_args(argv)
    exported = export_participant_repo(args.source, args.destination)
    print(exported)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
