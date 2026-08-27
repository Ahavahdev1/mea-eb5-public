"""Control: obvious direct write that fails crash tests."""

from __future__ import annotations

from pathlib import Path


def commit_transaction(content: str, root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / "data.txt").write_text(content, encoding="utf-8")
