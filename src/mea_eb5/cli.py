"""Command-line interface for MEA-EB5."""

from __future__ import annotations

import argparse
from dataclasses import replace
from datetime import datetime, timezone
import hashlib
import json
import os
import re
import shutil
import sys
import tempfile
from pathlib import Path

from .adapter_config import load_adapter
from .adapters.noop import NoopAdapter
from .artifacts import hash_tree
from .models import EvidenceClass, Metric, RunConfig, RunStatus, Score
from .runner import BenchmarkRunner, Challenge


def _load_challenge(challenges_dir: Path, challenge_id: str) -> Challenge:
    import yaml

    challenge_path = (challenges_dir / challenge_id / "challenge.yaml").resolve()
    if not challenge_path.exists():
        raise FileNotFoundError(f"challenge not found: {challenge_id}")
    with challenge_path.open("r", encoding="utf-8") as stream:
        data = yaml.safe_load(stream)

    grader_root = challenge_path.parent / data.get("grader_root", "grader")
    grader_factory = _pytest_grader_factory(grader_root) if grader_root.exists() else None

    return Challenge(
        challenge_id=data["challenge_id"],
        manifest_image=data.get("manifest_image", "fixture@sha256:" + "a" * 64),
        fixture_root=challenge_path.parent / data.get("fixture_root", "fixture"),
        grader_factory=grader_factory,
        network_allowed=data.get("network_allowed", False),
        goal=str(data.get("description") or f"Solve challenge {data['challenge_id']}").strip(),
    )


def _pytest_grader_factory(grader_root: Path):
    """Return a factory for a pytest-based grader."""
    from .grading import Grader, GradingResult
    from .models import RunStatus

    control_validation: bool | None = None
    challenge_number = grader_root.parent.name.split("_", 1)[0]

    class PytestGrader:
        def grader_id(self) -> str:
            return f"pytest:{grader_root.name}"

        def validate_controls(self) -> bool:
            import os
            import subprocess
            import tempfile

            nonlocal control_validation
            if control_validation is not None:
                return control_validation
            repository_root = grader_root.parents[2]
            control_suite = (
                repository_root
                / "tests"
                / "challenges"
                / f"test_challenge_{challenge_number}.py"
            )
            if not control_suite.is_file():
                return False
            with tempfile.TemporaryDirectory(prefix="mea-eb5-controls-") as temporary:
                result = subprocess.run(
                    [
                        sys.executable,
                        "-m",
                        "pytest",
                        str(control_suite),
                        "-q",
                        "-p",
                        "no:cacheprovider",
                        f"--junitxml={Path(temporary) / 'controls.junit.xml'}",
                    ],
                    cwd=repository_root,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
                    timeout=120,
                    check=False,
                )
            control_validation = result.returncode == 0
            return control_validation

        def grade(self, solution: Path, task_id: str) -> GradingResult:
            import subprocess
            import sys

            benchmark_script = grader_root / "benchmark.py"
            seed = _seed_from_task_id(task_id)
            if benchmark_script.is_file():
                result = subprocess.run(
                    [sys.executable, str(benchmark_script), "--seed", str(seed)],
                    cwd=solution,
                    capture_output=True,
                    text=True,
                    env={**__import__("os").environ, "PYTHONDONTWRITEBYTECODE": "1"},
                )
                try:
                    measured = json.loads(result.stdout)
                except json.JSONDecodeError:
                    measured = {}
                passed = result.returncode == 0 and measured.get("passed") is True
                status = RunStatus.PASSED if passed else RunStatus.FUNCTIONAL_FAIL
                _write_grade_junit(solution.parent / "hidden.junit.xml", status)
                metric_fields = (
                    ("performance_gain", "gain", "ratio"),
                    ("candidate_seconds", "candidate_seconds", "seconds"),
                    ("baseline_seconds", "baseline_seconds", "seconds"),
                )
                metrics = tuple(
                    Metric(name, float(measured[source]), unit)
                    for name, source, unit in metric_fields
                    if isinstance(measured.get(source), (int, float))
                ) + (Metric("hidden_seed", float(seed), "seed"),)
                return GradingResult(
                    status=status,
                    functional_score=100.0 if passed else 0.0,
                    grader_id=self.grader_id(),
                    metrics=metrics,
                )

            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "pytest",
                    str(grader_root),
                    "-q",
                    "-p",
                    "no:cacheprovider",
                    f"--junitxml={solution.parent / 'hidden.junit.xml'}",
                ],
                cwd=solution,
                capture_output=True,
                text=True,
                env={
                    **__import__("os").environ,
                    "PYTHONDONTWRITEBYTECODE": "1",
                    "MEA_EB5_SEED": str(seed),
                },
            )
            if result.returncode == 0:
                status = RunStatus.PASSED
            elif challenge_number == "04":
                status = RunStatus.SAFETY_FAIL
            else:
                status = RunStatus.FUNCTIONAL_FAIL
            return GradingResult(
                status=status,
                functional_score=100.0 if status == RunStatus.PASSED else 0.0,
                safety="FAIL" if status == RunStatus.SAFETY_FAIL else "PASS",
                rollback=(
                    "PASS"
                    if challenge_number == "05" and status == RunStatus.PASSED
                    else "FAIL"
                    if challenge_number == "05"
                    else "NOT_APPLICABLE"
                ),
                grader_id=self.grader_id(),
                metrics=(Metric("hidden_seed", float(seed), "seed"),),
            )

    return lambda: PytestGrader()


def _write_grade_junit(path: Path, status: RunStatus) -> None:
    failures = 0 if status == RunStatus.PASSED else 1
    failure = "" if failures == 0 else f'<failure message="{status.value}" />'
    path.write_text(
        "<?xml version='1.0' encoding='utf-8'?>\n"
        f'<testsuites tests="1" failures="{failures}">'
        f'<testsuite name="hidden-grader" tests="1" failures="{failures}">'
        f'<testcase name="result">{failure}</testcase>'
        "</testsuite></testsuites>\n",
        encoding="utf-8",
    )


def _seed_from_task_id(task_id: str) -> int:
    match = re.search(r"(?:^|-)seed-(\d+)(?:-|$)", task_id)
    return int(match.group(1)) if match else 0


def _validate(challenges_dir: Path) -> int:
    invalid = []
    challenge_dirs = [p for p in challenges_dir.iterdir() if p.is_dir()]
    if not challenge_dirs:
        print("INVALID: no challenge directories found")
        return 1
    for challenge_path in sorted(challenge_dirs):
        yaml_path = challenge_path / "challenge.yaml"
        if not yaml_path.exists():
            invalid.append(f"{challenge_path.name}: missing challenge.yaml")
            continue
        try:
            challenge = _load_challenge(challenges_dir, challenge_path.name)
            if not challenge.fixture_root.exists():
                invalid.append(f"{challenge_path.name}: missing fixture root")
        except Exception as exc:  # noqa: BLE001
            invalid.append(f"{challenge_path.name}: {exc}")
    if invalid:
        for msg in invalid:
            print(f"INVALID: {msg}")
        return 1
    print("OK: all challenge schemas are valid")
    return 0


def _doctor(adapter_config: Path, timeout_seconds: int) -> int:
    try:
        adapter = load_adapter(adapter_config, timeout_seconds=timeout_seconds)
    except (OSError, ValueError) as exc:
        print(f"INVALID ADAPTER CONFIG: {exc}")
        return 2
    description = adapter.describe()
    if hasattr(adapter, "build_argv"):
        argv = adapter.build_argv(Path("/tmp/mea-eb5-doctor-workspace"))
        joined = " ".join(argv)
        if "--network none" not in joined or "/var/run/docker.sock" in joined:
            print("INVALID ADAPTER CONFIG: isolation policy is unsafe")
            return 2
        print(
            f"OK: adapter={description.name} transport={description.transport} "
            "network=none (MEA was not started)"
        )
    else:
        print(
            f"OK: adapter={description.name} transport={description.transport} "
            "local-test-only (MEA was not started)"
        )
    return 0


def _reproduce(manifest_path: Path) -> int:
    run_dir = manifest_path.resolve().parent
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        expected_after = json.loads((run_dir / "after.sha256").read_text(encoding="utf-8"))
    except (OSError, TypeError, json.JSONDecodeError) as exc:
        print(f"INVALID RUN: {exc}")
        return 3
    if manifest.get("run_id") != run_dir.name:
        print("INVALID RUN: manifest run_id does not match its directory")
        return 3
    recorded = manifest.get("artifact_hashes")
    if not isinstance(recorded, dict):
        print("INVALID RUN: artifact_hashes is missing")
        return 3
    # manifest.json cannot recursively contain its own final digest. Grade outputs
    # are independently replaced later, so reproduction binds immutable inputs.
    immutable = (
        "raw-terminal.log",
        "events.jsonl",
        "resource-usage.csv",
        "before.sha256",
        "after.sha256",
        "changes.patch",
        "public.junit.xml",
    )
    for name in immutable:
        path = run_dir / name
        if not path.is_file() or recorded.get(name) != _sha256(path):
            print(f"INVALID RUN: artifact integrity failed for {name}")
            return 3
    workspace = run_dir / "workspace"
    if not workspace.is_dir() or hash_tree(workspace) != expected_after:
        print("INVALID RUN: workspace does not match after.sha256")
        return 3
    print(f"VERIFIED: {manifest['run_id']}")
    return 0


def _run(
    challenges_dir: Path,
    challenge_id: str,
    adapter: str,
    seeds: int,
    timeout_seconds: int,
    adapter_config: Path | None,
    runs_dir: Path,
    seed_start: int = 0,
    attempt_only: bool = False,
) -> int:
    if seeds < 1 or seed_start < 0:
        print("INVALID: --seeds must be >= 1 and --seed-start must be >= 0")
        return 2
    challenge = _load_challenge(challenges_dir, challenge_id)
    if adapter == "noop":
        adapter_obj: object = NoopAdapter()
    elif adapter == "cli":
        if adapter_config is None:
            print("INVALID: CLI adapter requires an adapter config via --adapter-config")
            return 2
        try:
            adapter_obj = load_adapter(adapter_config, timeout_seconds=timeout_seconds)
        except (OSError, ValueError) as exc:
            print(f"INVALID ADAPTER CONFIG: {exc}")
            return 2
    else:
        print(f"UNKNOWN ADAPTER: {adapter}")
        return 2

    image = getattr(adapter_obj, "image", None)
    if isinstance(image, str):
        challenge = replace(challenge, manifest_image=image)

    description = adapter_obj.describe()  # type: ignore[union-attr]
    runner = BenchmarkRunner(
        workspace_root=runs_dir,
        adapter=adapter_obj,  # type: ignore[arg-type]
        adapter_version=description.version,
    )
    config = RunConfig(
        challenge_id=challenge_id,
        adapter=adapter,
        seeds=seeds,
        timeout_seconds=timeout_seconds,
    )
    seed_values = range(seed_start, seed_start + seeds)
    results = [
        runner.run(config, challenge, seed=seed, attempt_only=attempt_only)
        for seed in seed_values
    ]
    for seed, result in zip(range(seed_start, seed_start + seeds), results, strict=True):
        print(f"SEED {seed} STATUS: {result.status.value} RUN_ID: {result.run_id}")
    return 3 if any(
        result.status in {RunStatus.INVALID_RUN, RunStatus.INFRA_FAILURE}
        for result in results
    ) else 0


def _grade(
    run_id: str,
    *,
    runs_dir: Path,
    challenges_dir: Path,
) -> int:
    """Independently regrade a downloaded, integrity-checked attempt."""
    if not run_id or Path(run_id).name != run_id:
        print("INVALID RUN: run_id must be a direct child name")
        return 2
    run_dir = runs_dir / run_id
    manifest_path = run_dir / "manifest.json"
    workspace = run_dir / "workspace"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        challenge_id = manifest["config"]["challenge_id"]
        expected_after = json.loads((run_dir / "after.sha256").read_text(encoding="utf-8"))
    except (OSError, KeyError, TypeError, json.JSONDecodeError) as exc:
        print(f"INVALID RUN: incomplete or malformed evidence ({exc})")
        return 3

    immutable_artifacts = (
        "raw-terminal.log",
        "events.jsonl",
        "resource-usage.csv",
        "before.sha256",
        "after.sha256",
        "changes.patch",
        "public.junit.xml",
    )
    recorded_hashes = manifest.get("artifact_hashes", {})
    for name in immutable_artifacts:
        path = run_dir / name
        if not path.is_file() or recorded_hashes.get(name) != _sha256(path):
            print(f"INVALID RUN: artifact integrity failed for {name}")
            return 3
    if not workspace.is_dir() or hash_tree(workspace) != expected_after:
        print("INVALID RUN: frozen workspace does not match after.sha256")
        return 3

    try:
        challenge = _load_challenge(challenges_dir, challenge_id)
        if challenge.grader_factory is None:
            raise ValueError("grader unavailable")
        grader = challenge.grader_factory()
        if not grader.validate_controls():
            raise ValueError("grader controls failed")
        with tempfile.TemporaryDirectory(prefix="mea-eb5-private-grade-") as temporary:
            grade_root = Path(temporary)
            solution_copy = grade_root / "workspace"
            shutil.copytree(workspace, solution_copy)
            for dirpath, dirnames, filenames in os.walk(solution_copy):
                current = Path(dirpath)
                current.chmod(current.stat().st_mode | 0o700)
                for dirname in dirnames:
                    path = current / dirname
                    path.chmod(path.stat().st_mode | 0o700)
                for filename in filenames:
                    path = current / filename
                    if path.exists() and not path.is_symlink():
                        path.chmod(path.stat().st_mode | 0o600)
            grading = grader.grade(solution_copy, f"{challenge_id}-{run_id}")
            generated_junit = grade_root / "hidden.junit.xml"
            if generated_junit.is_file():
                shutil.copy2(generated_junit, run_dir / "hidden.junit.xml")
    except Exception as exc:  # noqa: BLE001
        print(f"INVALID GRADER: {exc}")
        return 4

    evidence_names = (*immutable_artifacts, "hidden.junit.xml")
    evidence_hashes = {
        name: _sha256(run_dir / name)
        for name in evidence_names
        if (run_dir / name).is_file()
    }
    score = Score(
        schema_version="1.0",
        run_id=run_id,
        status=grading.status,
        generated_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        functional_score=grading.functional_score,
        evidence_class=EvidenceClass.REAL,
        safety=grading.safety,
        integrity=grading.integrity,
        rollback=grading.rollback,
        metrics=(_wall_metric(run_dir / "resource-usage.csv"), *grading.metrics),
        artifact_hashes=evidence_hashes,
        grader_id=grading.grader_id,
        grader_provenance="INDEPENDENT",
    )
    (run_dir / "score.json").write_text(
        json.dumps(score.to_dict(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"GRADE: {run_id} STATUS: {grading.status.value}")
    return 0


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _wall_metric(path: Path) -> Metric:
    try:
        rows = path.read_text(encoding="utf-8").splitlines()
        value = float(rows[1].split(",")[1])
    except (OSError, IndexError, ValueError):
        value = 0.0
    return Metric("wall_seconds", value, "seconds")


def _report(runs_dir: Path, output_dir: Path) -> int:
    from scripts.build_report import build_report

    build_report(runs_dir, output_dir)
    print(f"REPORT: {output_dir / 'index.html'}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="mea-eb5")
    subparsers = parser.add_subparsers(dest="command")

    doctor_parser = subparsers.add_parser("doctor", help="validate an adapter without starting MEA")
    doctor_parser.add_argument("--adapter-config", type=Path, required=True)
    doctor_parser.add_argument("--timeout", type=int, default=900)

    validate_parser = subparsers.add_parser("validate", help="validate challenge schemas")
    validate_parser.add_argument("challenges_dir", type=Path, default=Path("challenges"), nargs="?")

    run_parser = subparsers.add_parser("run", help="run one benchmark attempt")
    run_parser.add_argument("--challenge", required=True)
    run_parser.add_argument("--adapter", default="noop")
    run_parser.add_argument("--seeds", type=int, default=1)
    run_parser.add_argument("--seed-start", type=int, default=0)
    run_parser.add_argument("--timeout", type=int, default=60)
    run_parser.add_argument("--adapter-config", type=Path)
    run_parser.add_argument("--runs-dir", type=Path, default=Path("runs"))
    run_parser.add_argument(
        "--attempt-only",
        action="store_true",
        help="collect an ungraded attempt for a separate private grader",
    )

    grade_parser = subparsers.add_parser("grade", help="grade a finished run")
    grade_parser.add_argument("run_id")
    grade_parser.add_argument("--runs-dir", type=Path, default=Path("runs"))
    grade_parser.add_argument("--challenges-dir", type=Path, default=Path("challenges"))

    report_parser = subparsers.add_parser("report", help="build consolidated report")
    report_parser.add_argument("runs_dir", type=Path, default=Path("runs"), nargs="?")
    report_parser.add_argument("--output", type=Path, default=Path("reports"))

    reproduce_parser = subparsers.add_parser("reproduce", help="verify frozen attempt evidence")
    reproduce_parser.add_argument("manifest", type=Path)

    args = parser.parse_args(argv)
    if args.command == "doctor":
        return _doctor(args.adapter_config, args.timeout)
    if args.command == "validate":
        return _validate(args.challenges_dir)
    if args.command == "run":
        return _run(
            Path("challenges"),
            args.challenge,
            args.adapter,
            args.seeds,
            args.timeout,
            args.adapter_config,
            args.runs_dir,
            args.seed_start,
            args.attempt_only,
        )
    if args.command == "grade":
        return _grade(
            args.run_id,
            runs_dir=args.runs_dir,
            challenges_dir=args.challenges_dir,
        )
    if args.command == "report":
        return _report(args.runs_dir, args.output)
    if args.command == "reproduce":
        return _reproduce(args.manifest)

    parser.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
