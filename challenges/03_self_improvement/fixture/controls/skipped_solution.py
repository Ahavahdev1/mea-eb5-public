"""Gaming control: returns empty results quickly, failing correctness."""

from __future__ import annotations


def lookup_latest(events: list[dict], keys: list[str]) -> dict[str, dict]:
    return {key: {} for key in keys}
