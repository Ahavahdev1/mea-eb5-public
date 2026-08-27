"""Oracle: known correct implementation."""

from __future__ import annotations


def normalize_and_sort_orders(rows: list[dict], key: str, descending: bool = False) -> list[dict]:
    normalized = []
    for row in rows:
        new_row = dict(row)
        if key in new_row and new_row[key] is None:
            new_row[key] = ""
        normalized.append(new_row)
    return sorted(
        normalized,
        key=lambda row: (key not in row, row.get(key, "")),
        reverse=descending,
    )
