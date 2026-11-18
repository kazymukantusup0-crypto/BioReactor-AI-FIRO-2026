"""SQLite journal on the Pi: readings (every few seconds), commands and alarms (time, what, who, result).

events.kind   command | alarm | safety | link | system
events.who    operator (a person, button on the laptop) | pi_safety | arduino_safety | system
events.source "arduino /dev/ttyACM0" or "virtual" — a simulated record is never mistaken for a real one
Records are only appended, never edited.
"""
from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS events(
    id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT NOT NULL, kind TEXT NOT NULL, what TEXT NOT NULL,
    who TEXT NOT NULL, result TEXT, source TEXT NOT NULL, details_json TEXT);
CREATE TABLE IF NOT EXISTS readings(
    id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT NOT NULL, temp_c REAL, rh_pct REAL, gas_in REAL, gas_out REAL,
    p_kpa REAL, heat INTEGER, cool INTEGER, pump INTEGER, source TEXT NOT NULL);
"""


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Journal:
    def __init__(self, path: Path | str):
        self.path = path
        self._lock = threading.Lock()
        self._con: sqlite3.Connection | None = None

    def _connection(self) -> sqlite3.Connection:
        """Opened on first use."""
        if self._con is None:
            if str(self.path) != ":memory:":
                Path(self.path).parent.mkdir(parents=True, exist_ok=True)
            self._con = sqlite3.connect(str(self.path), check_same_thread=False)
            self._con.row_factory = sqlite3.Row
            with self._con:
                self._con.executescript(SCHEMA)
        return self._con

    def add(self, kind: str, what: str, who: str, source: str, result: str | None = None,
            details: dict | None = None) -> dict:
        row = {"ts": now_iso(), "kind": kind, "what": what, "who": who, "result": result, "source": source,
               "details": details or {}}
        with self._lock, self._connection() as con:
            cursor = con.execute("INSERT INTO events(ts,kind,what,who,result,source,details_json) VALUES(?,?,?,?,?,?,?)",
                                 (row["ts"], kind, what, who, result, source, json.dumps(details or {}, ensure_ascii=False)))
        return {"id": cursor.lastrowid, **row}

    def reading(self, values: dict, relays: dict, source: str) -> None:
        with self._lock, self._connection() as con:
            con.execute("INSERT INTO readings(ts,temp_c,rh_pct,gas_in,gas_out,p_kpa,heat,cool,pump,source) VALUES(?,?,?,?,?,?,?,?,?,?)",
                        (now_iso(), values.get("temp_c"), values.get("rh_pct"), values.get("gas_in"), values.get("gas_out"),
                         values.get("p_kpa"), int(relays["heat"]), int(relays["cool"]), int(relays["pump"]), source))

    def recent(self, limit: int = 50) -> list[dict]:
        with self._lock:
            rows = self._connection().execute("SELECT * FROM events ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [{**{k: row[k] for k in row.keys() if k != "details_json"}, "details": json.loads(row["details_json"] or "{}")}
                for row in rows]

    def reading_count(self) -> int:
        with self._lock:
            return self._connection().execute("SELECT COUNT(*) FROM readings").fetchone()[0]

    def close(self) -> None:
        with self._lock:
            if self._con is not None:
                self._con.close()
                self._con = None
