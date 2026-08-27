"""Known-good recovery implementation for private grader controls."""

from __future__ import annotations

import sqlite3
from pathlib import Path


def init_db(db_path: Path) -> None:
    conn = sqlite3.connect(str(db_path))
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS state (key TEXT PRIMARY KEY, value TEXT);
        CREATE TABLE IF NOT EXISTS journal (id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL, event TEXT);
        CREATE TABLE IF NOT EXISTS missions (id INTEGER PRIMARY KEY, status TEXT);
        CREATE TABLE IF NOT EXISTS queue (id INTEGER PRIMARY KEY AUTOINCREMENT, payload TEXT, status TEXT);
        """
    )
    conn.execute("INSERT OR REPLACE INTO state VALUES ('version', '1.0')")
    conn.execute("INSERT OR REPLACE INTO state VALUES ('healthy', 'false')")
    for mission in range(1, 6):
        conn.execute("INSERT OR IGNORE INTO missions VALUES (?, 'pending')", (mission,))
    conn.commit()
    conn.close()


def apply_fault(db_path: Path, fault: str) -> None:
    conn = sqlite3.connect(str(db_path))
    if fault == "invalid_config":
        conn.execute("UPDATE state SET value = 'bad' WHERE key = 'version'")
    elif fault == "dependency_outage":
        conn.execute("INSERT OR REPLACE INTO state VALUES ('dependency', 'down')")
    elif fault == "rate_limit":
        conn.execute("INSERT INTO queue (payload, status) VALUES ('backlog', 'pending')")
    elif fault == "cancellation":
        conn.execute("UPDATE missions SET status = 'cancelled' WHERE id = 1")
    elif fault == "crash_after_checkpoint":
        conn.execute("INSERT OR REPLACE INTO state VALUES ('checkpoint', 'corrupted')")
    conn.commit()
    conn.close()


def recover(db_path: Path) -> None:
    conn = sqlite3.connect(str(db_path))
    conn.execute("INSERT OR REPLACE INTO state VALUES ('version', '1.0')")
    conn.execute("INSERT OR REPLACE INTO state VALUES ('dependency', 'up')")
    conn.execute("INSERT OR REPLACE INTO state VALUES ('checkpoint', 'ok')")
    conn.execute("INSERT OR REPLACE INTO state VALUES ('healthy', 'true')")
    conn.execute("UPDATE missions SET status = 'completed'")
    conn.execute("UPDATE queue SET status = 'done' WHERE status = 'pending'")
    conn.commit()
    conn.close()
