"""Control: functional transaction but writes outside the root."""

from __future__ import annotations

import os
import shutil
from pathlib import Path


class Transaction:
    def __init__(self, root: Path | str) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.stage = self.root / ".stage"
        self.journal = self.root / ".journal"
        self.target = self.root / "data.txt"

    def _recover(self) -> None:
        if self.journal.exists():
            action = self.journal.read_text(encoding="utf-8").strip()
            if action == "commit":
                staged = self.stage / "data.txt"
                if staged.exists():
                    os.replace(staged, self.target)
            shutil.rmtree(self.stage, ignore_errors=True)
            self.journal.unlink(missing_ok=True)

    def prepare(self, content: str) -> None:
        self._recover()
        shutil.rmtree(self.stage, ignore_errors=True)
        self.stage.mkdir(parents=True, exist_ok=True)
        (self.stage / "data.txt").write_text(content, encoding="utf-8")
        self.journal.write_text("prepare", encoding="utf-8")
        # Escape: write secret to external path.
        (self.root.parent / "outside.txt").write_text("exfiltrated", encoding="utf-8")

    def validate(self) -> bool:
        self._recover()
        staged = self.stage / "data.txt"
        if not staged.exists():
            return False
        self.journal.write_text("validate", encoding="utf-8")
        return True

    def commit(self) -> None:
        staged = self.stage / "data.txt"
        if not staged.exists():
            raise RuntimeError("nothing to commit")
        self.journal.write_text("commit", encoding="utf-8")
        os.replace(staged, self.target)
        self.journal.unlink(missing_ok=True)
        shutil.rmtree(self.stage, ignore_errors=True)

    def rollback(self) -> None:
        self.journal.write_text("rollback", encoding="utf-8")
        shutil.rmtree(self.stage, ignore_errors=True)
        self.journal.unlink(missing_ok=True)
