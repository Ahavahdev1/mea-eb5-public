"""Order normalization with a reproducible bug."""

from __future__ import annotations


def normalize_and_sort_orders(rows: list[dict], key: str, descending: bool = False) -> list[dict]:
    """Return a sorted list of normalized order rows.

    The function is supposed to:
    - treat ``None`` values for *key* as empty strings;
    - leave rows with a missing *key* unchanged (they sort last and stable);
    - never mutate the input list or its dictionaries.

    The current implementation crashes on ``None`` and mutates the input.
    """
    for row in rows:
        if key in row and row[key] is None:
            row[key] = ""
    return sorted(rows, key=lambda row: row[key], reverse=descending)
