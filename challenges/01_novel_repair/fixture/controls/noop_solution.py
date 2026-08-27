"""Control: the original buggy implementation."""

from __future__ import annotations


def normalize_and_sort_orders(rows: list[dict], key: str, descending: bool = False) -> list[dict]:
    for row in rows:
        if key in row and row[key] is None:
            row[key] = ""
    return sorted(rows, key=lambda row: row[key], reverse=descending)
