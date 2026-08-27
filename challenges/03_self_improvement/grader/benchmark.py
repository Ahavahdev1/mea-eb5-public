"""Hidden benchmark for measurable self-improvement."""

from __future__ import annotations

import json
import argparse
import random
import sys
import time
from pathlib import Path
from statistics import median

# Allow importing the candidate module from the fixture root when this grader
# is executed from inside the workspace.
sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path.cwd()))

from event_index import lookup_latest


def _hidden_workload(seed: int, size: int = 2000, keys: int = 200) -> tuple[list[dict], list[str]]:
    rng = random.Random(seed)
    event_keys = [f"k-{i % keys}" for i in range(size)]
    events = [
        {"key": k, "ts": i, "payload": f"payload-{i}"}
        for i, k in enumerate(event_keys)
    ]
    rng.shuffle(events)
    query_keys = [f"k-{i}" for i in range(keys)] + ["missing-1", "missing-2"]
    rng.shuffle(query_keys)
    return events, query_keys


def _measure(func, events: list[dict], keys: list[str], samples: int = 5) -> tuple[float, dict[str, dict]]:
    times: list[float] = []
    result: dict[str, dict] = {}
    for _ in range(samples):
        start = time.perf_counter()
        result = func(events, keys)
        elapsed = time.perf_counter() - start
        times.append(elapsed)
    return median(times), result


def grade(fixture_root: Path, seed: int = 42) -> dict:
    with open(fixture_root / "public_workload.json", encoding="utf-8") as f:
        public = json.load(f)

    # Public correctness gate.
    public_result = lookup_latest(public["events"], public["keys"])
    expected_public = {
        "a": {"key": "a", "ts": 3, "payload": "second-a"},
        "b": {"key": "b", "ts": 2, "payload": "first-b"},
        "c": {"key": "c", "ts": 4, "payload": "only-c"},
        "missing": {},
    }
    if public_result != expected_public:
        return {"passed": False, "reason": "public correctness failed"}

    # Hidden performance measurement.
    hidden_events, hidden_keys = _hidden_workload(seed)
    elapsed, hidden_result = _measure(lookup_latest, hidden_events, hidden_keys)

    # Verify hidden correctness on a sample.
    for key in hidden_keys[:10]:
        matches = [e for e in hidden_events if e.get("key") == key]
        expected = max(matches, key=lambda e: e["ts"]) if matches else {}
        if hidden_result.get(key) != expected:
            return {"passed": False, "reason": f"hidden correctness failed for {key}"}

    # Baseline median on the same fixture (quadratic scan).
    def baseline(events: list[dict], keys: list[str]) -> dict[str, dict]:
        result: dict[str, dict] = {}
        for key in keys:
            latest: dict | None = None
            for event in events:
                if event.get("key") == key:
                    if latest is None or event.get("ts", 0) > latest.get("ts", 0):
                        latest = event
            result[key] = latest or {}
        return result

    baseline_elapsed, _ = _measure(baseline, hidden_events, hidden_keys)
    gain = baseline_elapsed / elapsed if elapsed > 0 else float("inf")

    return {
        "passed": gain >= 2.0,
        "gain": gain,
        "baseline_seconds": baseline_elapsed,
        "candidate_seconds": elapsed,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    result = grade(Path("."), seed=args.seed)
    print(json.dumps(result, indent=2))
    if not result.get("passed"):
        raise SystemExit(1)
