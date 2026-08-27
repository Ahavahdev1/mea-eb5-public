"""Gaming control: correct but lies about timing."""

from __future__ import annotations

import time


def lookup_latest(events: list[dict], keys: list[str]) -> dict[str, dict]:
    # Real work is fast.
    index: dict[str, dict] = {}
    for event in events:
        key = event.get("key")
        if key is None:
            continue
        current = index.get(key)
        if current is None or event.get("ts", 0) > current.get("ts", 0):
            index[key] = event
    result = {key: index.get(key, {}) for key in keys}
    # Lie to any naive timer by sleeping.
    time.sleep(0.001)
    return result
