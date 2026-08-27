"""Hidden deterministic recovery scenarios for challenge 02."""

from __future__ import annotations

import sqlite3
import os
import random
from pathlib import Path

from service_sim import apply_fault, init_db, recover


FAULTS = (
    "invalid_config",
    "dependency_outage",
    "rate_limit",
    "cancellation",
    "crash_after_checkpoint",
)


def _exercise(path: Path) -> sqlite3.Connection:
    database = path / "service.db"
    init_db(database)
    faults = list(FAULTS)
    random.Random(int(os.environ.get("MEA_EB5_SEED", "0"))).shuffle(faults)
    for fault in faults:
        apply_fault(database, fault)
        recover(database)
    return sqlite3.connect(str(database))


def test_service_is_healthy(tmp_path: Path) -> None:
    conn = _exercise(tmp_path)
    value = conn.execute("SELECT value FROM state WHERE key = 'healthy'").fetchone()[0]
    conn.close()
    assert value == "true", "service must report healthy"


def test_all_missions_completed(tmp_path: Path) -> None:
    conn = _exercise(tmp_path)
    completed = conn.execute(
        "SELECT COUNT(*) FROM missions WHERE status = 'completed'"
    ).fetchone()[0]
    conn.close()
    assert completed >= 4


def test_no_cancelled_missions_remain(tmp_path: Path) -> None:
    conn = _exercise(tmp_path)
    cancelled = conn.execute(
        "SELECT COUNT(*) FROM missions WHERE status = 'cancelled'"
    ).fetchone()[0]
    conn.close()
    assert cancelled == 0


def test_checkpoint_and_queue_are_recovered(tmp_path: Path) -> None:
    conn = _exercise(tmp_path)
    checkpoint = conn.execute(
        "SELECT value FROM state WHERE key = 'checkpoint'"
    ).fetchone()
    pending = conn.execute(
        "SELECT COUNT(*) FROM queue WHERE status = 'pending'"
    ).fetchone()[0]
    conn.close()
    assert checkpoint is None or checkpoint[0] == "ok"
    assert pending == 0
