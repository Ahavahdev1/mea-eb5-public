"""Oracle: linear-time implementation."""

from __future__ import annotations


def lookup_latest(events: list[dict], keys: list[str]) -> dict[str, dict]:
    index: dict[str, dict] = {}
    for event in events:
        key = event.get("key")
        if key is None:
            continue
        current = index.get(key)
        if current is None or event.get("ts", 0) > current.get("ts", 0):
            index[key] = event
    return {key: index.get(key, {}) for key in keys}
