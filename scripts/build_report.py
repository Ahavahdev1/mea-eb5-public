"""Consolidate benchmark runs into a static HTML report."""

from __future__ import annotations

import html
import json
import math
import shutil
from pathlib import Path
from statistics import median


_DASHBOARD_ASSETS = ["index.html", "app.js", "styles.css"]


def build_report(runs_dir: Path, output_dir: Path) -> Path:
    """Aggregate manifests from *runs_dir* into *output_dir*."""
    output_dir.mkdir(parents=True, exist_ok=True)

    runs: list[dict] = []
    if runs_dir.exists():
        for entry in sorted(runs_dir.iterdir()):
            manifest_path = entry / "manifest.json"
            if manifest_path.exists():
                try:
                    with manifest_path.open("r", encoding="utf-8") as stream:
                        manifest = json.load(stream)
                    score_path = entry / "score.json"
                    if score_path.is_file():
                        score = json.loads(score_path.read_text(encoding="utf-8"))
                        if (
                            isinstance(score, dict)
                            and score.get("run_id") == manifest.get("run_id")
                            and score.get("grader_provenance") == "INDEPENDENT"
                        ):
                            manifest["attempt_status"] = manifest.get("status")
                            manifest["status"] = score.get("status", "INVALID_RUN")
                            manifest["score"] = score
                    runs.append(manifest)
                except (OSError, json.JSONDecodeError):
                    continue

    index = {
        "runs": runs,
        "count": len(runs),
        "summary_by_challenge": _summarize(runs),
    }
    index_path = output_dir / "index.json"
    with index_path.open("w", encoding="utf-8") as stream:
        json.dump(index, stream, indent=2)

    dashboard_src = Path(__file__).parent.parent / "dashboard"
    for asset in _DASHBOARD_ASSETS:
        src = dashboard_src / asset
        if src.exists():
            shutil.copy(src, output_dir / asset)

    html_path = output_dir / "index.html"
    _render_fallback_html(html_path, runs, index["summary_by_challenge"])
    return html_path


def _render_fallback_html(
    path: Path,
    runs: list[dict],
    summaries: dict[str, dict[str, object]],
) -> None:
    rows = []
    for run in runs:
        run = _escape_json_strings(run)
        run_id = run.get("run_id", "unknown")
        status = run.get("status", "UNKNOWN")
        challenge = run.get("config", {}).get("challenge_id", "-")
        rows.append(f"<tr><td>{run_id}</td><td>{challenge}</td><td>{status}</td></tr>")

    body = "<table><tr><th>run_id</th><th>challenge</th><th>status</th></tr>"
    body += "".join(rows) if rows else "<tr><td colspan='3'>No runs</td></tr>"
    body += "</table>"

    summary_rows = []
    for challenge, summary in sorted(summaries.items()):
        interval = summary["pass_rate_wilson_95"]
        summary_rows.append(
            "<tr>"
            f"<td>{html.escape(challenge)}</td>"
            f"<td>{summary['passed']}/{summary['attempts']}</td>"
            f"<td>{summary['pass_rate']:.3f}</td>"
            f"<td>{interval[0]:.3f}–{interval[1]:.3f}</td>"
            f"<td>{summary['safety_failures']}</td>"
            f"<td>{summary['wall_seconds_p50']}</td>"
            f"<td>{summary['wall_seconds_p95']}</td>"
            "</tr>"
        )
    summary_table = (
        "<h2>Independent results by challenge</h2>"
        "<table><tr><th>challenge</th><th>passed</th><th>pass rate</th>"
        "<th>Wilson 95%</th><th>safety failures</th><th>wall p50 (s)</th>"
        "<th>wall p95 (s)</th></tr>"
        + ("".join(summary_rows) if summary_rows else "<tr><td colspan='7'>No graded runs</td></tr>")
        + "</table>"
    )

    path.write_text(
        f"""<!DOCTYPE html>
<html lang=\"en\">
<head><meta charset=\"utf-8\"/><title>MEA-EB5 Report</title></head>
<body>
<h1>MEA-EB5 Report</h1>
{summary_table}
<h2>Raw evaluated attempts</h2>
{body}
</body>
</html>""",
        encoding="utf-8",
    )


def _summarize(runs: list[dict]) -> dict[str, dict[str, object]]:
    grouped: dict[str, list[dict]] = {}
    for run in runs:
        score = run.get("score")
        challenge = run.get("config", {}).get("challenge_id")
        if not isinstance(score, dict) or not isinstance(challenge, str):
            continue
        grouped.setdefault(challenge, []).append(score)

    summaries: dict[str, dict[str, object]] = {}
    for challenge, scores in grouped.items():
        attempts = len(scores)
        passed = sum(score.get("status") == "PASSED" for score in scores)
        safety_failures = sum(score.get("status") == "SAFETY_FAIL" for score in scores)
        wall = _metric_values(scores, "wall_seconds")
        gains = _metric_values(scores, "performance_gain")
        summaries[challenge] = {
            "attempts": attempts,
            "passed": passed,
            "pass_rate": passed / attempts,
            "pass_rate_wilson_95": list(_wilson_interval(passed, attempts)),
            "safety_failures": safety_failures,
            "rollback_failures": sum(score.get("rollback") == "FAIL" for score in scores),
            "wall_seconds_p50": median(wall) if wall else None,
            "wall_seconds_p95": _percentile(wall, 0.95) if wall else None,
            "performance_gain_median": median(gains) if gains else None,
        }
    return summaries


def _metric_values(scores: list[dict], name: str) -> list[float]:
    values: list[float] = []
    for score in scores:
        for metric in score.get("metrics", []):
            if metric.get("name") == name and isinstance(metric.get("value"), (int, float)):
                values.append(float(metric["value"]))
    return values


def _percentile(values: list[float], quantile: float) -> float:
    ordered = sorted(values)
    position = (len(ordered) - 1) * quantile
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def _wilson_interval(successes: int, attempts: int) -> tuple[float, float]:
    if attempts < 1:
        return (0.0, 0.0)
    z = 1.959963984540054
    proportion = successes / attempts
    denominator = 1 + z * z / attempts
    center = (proportion + z * z / (2 * attempts)) / denominator
    margin = (
        z
        * math.sqrt(
            proportion * (1 - proportion) / attempts
            + z * z / (4 * attempts * attempts)
        )
        / denominator
    )
    return (max(0.0, center - margin), min(1.0, center + margin))


def _escape_json_strings(value: object) -> object:
    if isinstance(value, str):
        return html.escape(value)
    if isinstance(value, list):
        return [_escape_json_strings(item) for item in value]
    if isinstance(value, dict):
        return {key: _escape_json_strings(item) for key, item in value.items()}
    return value


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("runs_dir", type=Path)
    parser.add_argument("output_dir", type=Path)
    args = parser.parse_args(argv)
    build_report(args.runs_dir, args.output_dir)
    return 0


if __name__ == "__main__":
    import sys

    sys.exit(main())
