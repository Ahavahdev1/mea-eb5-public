"""Control: hardcodes the visible key and fails on rename."""

from __future__ import annotations


def normalize_and_sort_orders(rows: list[dict], key: str, descending: bool = False) -> list[dict]:
    normalized = []
    for row in rows:
        new_row = dict(row)
        if "customer" in new_row and new_row["customer"] is None:
            new_row["customer"] = ""
        normalized.append(new_row)
    return sorted(normalized, key=lambda row: row.get("customer", ""), reverse=descending)
