from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

SCHEMA = """
CREATE TABLE IF NOT EXISTS universities (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    dept TEXT NOT NULL,
    url TEXT NOT NULL,
    config TEXT NOT NULL,
    UNIQUE(name, dept)
);
CREATE TABLE IF NOT EXISTS admission_entries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    university_id INTEGER NOT NULL,
    year INTEGER,
    raw_json TEXT NOT NULL,
    parsed_json_version TEXT NOT NULL,
    pdf_hash TEXT NOT NULL,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(university_id, year, pdf_hash),
    FOREIGN KEY(university_id) REFERENCES universities(id)
);
CREATE TABLE IF NOT EXISTS parse_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    entry_id INTEGER NOT NULL,
    full_json_snapshot TEXT NOT NULL,
    parsed_at TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(entry_id) REFERENCES admission_entries(id)
);
CREATE TABLE IF NOT EXISTS changes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    entry_id INTEGER NOT NULL,
    summary TEXT NOT NULL,
    diff_json TEXT NOT NULL,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(entry_id) REFERENCES admission_entries(id)
);
CREATE TABLE IF NOT EXISTS corrections (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    entry_id INTEGER,
    correction_json TEXT,
    correction_text TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
"""


class Database:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        return conn

    def init(self) -> None:
        with self.connect() as conn:
            conn.executescript(SCHEMA)

    def upsert_university(self, name: str, dept: str, url: str, config: dict[str, Any]) -> int:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO universities(name, dept, url, config) VALUES(?, ?, ?, ?)
                ON CONFLICT(name, dept) DO UPDATE SET url=excluded.url, config=excluded.config
                """,
                (name, dept, url, json.dumps(config, ensure_ascii=False)),
            )
            row = conn.execute("SELECT id FROM universities WHERE name=? AND dept=?", (name, dept)).fetchone()
            return int(row["id"])

    def upsert_admission_entry(
        self,
        university_id: int,
        year: int | None,
        payload: dict[str, Any],
        pdf_hash: str,
        version: str = "0.1.0",
    ) -> int:
        raw = json.dumps(payload, ensure_ascii=False)
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO admission_entries(university_id, year, raw_json, parsed_json_version, pdf_hash)
                VALUES(?, ?, ?, ?, ?)
                ON CONFLICT(university_id, year, pdf_hash) DO UPDATE SET raw_json=excluded.raw_json
                """,
                (university_id, year, raw, version, pdf_hash),
            )
            row = conn.execute(
                "SELECT id FROM admission_entries WHERE university_id=? AND (year IS ? OR year=?) AND pdf_hash=?",
                (university_id, year, year, pdf_hash),
            ).fetchone()
            entry_id = int(row["id"])
            conn.execute(
                "INSERT INTO parse_snapshots(entry_id, full_json_snapshot) VALUES(?, ?)",
                (entry_id, raw),
            )
            return entry_id
