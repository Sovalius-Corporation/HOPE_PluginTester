"""SessionReport -- writes violation data to JSON and SQLite at session end.

Usage::

    r = SessionReport("reports")
    r.write_json(session_name, violations, stats)
    r.write_sqlite(session_name, violations, stats)
"""
from __future__ import annotations

import json
import logging
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Dict, List

logger = logging.getLogger(__name__)


class SessionReport:
    """Serialises violation lists to JSON and/or SQLite."""

    def __init__(self, output_dir: str = "reports") -> None:
        self._dir = Path(output_dir)
        self._dir.mkdir(parents=True, exist_ok=True)
        self._ts = datetime.now().strftime("%Y%m%d_%H%M%S")

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    def write_json(self, name: str, violations: List[dict], stats: Dict) -> str:
        path = self._dir / f"{name}_{self._ts}.json"
        data = {
            "session":    name,
            "timestamp":  self._ts,
            "stats":      {k: v for k, v in stats.items() if isinstance(v, (int, float, str, bool, type(None)))},
            "violations": self._clean(violations),
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, default=str)
        logger.info("JSON report: %s", path)
        return str(path)

    def write_sqlite(self, name: str, violations: List[dict], stats: Dict) -> str:
        path = self._dir / f"{name}_{self._ts}.db"
        con = sqlite3.connect(str(path))
        cur = con.cursor()
        cur.executescript("""
            CREATE TABLE IF NOT EXISTS sessions (
                id              INTEGER PRIMARY KEY,
                name            TEXT,
                ts              TEXT,
                total_violations INTEGER,
                duration_sec    REAL
            );
            CREATE TABLE IF NOT EXISTS violations (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id      INTEGER,
                type            TEXT,
                severity        TEXT,
                track_id        TEXT,
                license_plate   TEXT,
                speed_mph       REAL,
                frame_index     INTEGER,
                details         TEXT,
                FOREIGN KEY(session_id) REFERENCES sessions(id)
            );
        """)
        cur.execute(
            "INSERT INTO sessions VALUES (NULL,?,?,?,?)",
            (name, self._ts,
             stats.get("total_violations", 0),
             stats.get("duration_sec", 0.0)),
        )
        sid = cur.lastrowid
        for v in violations:
            cur.execute(
                "INSERT INTO violations VALUES (NULL,?,?,?,?,?,?,?,?)",
                (sid,
                 v.get("type", ""),
                 v.get("severity", ""),
                 str(v.get("track_id", "")),
                 v.get("license_plate", ""),
                 float(v.get("speed_mph") or v.get("max_speed_mph") or 0),
                 v.get("frame_index", 0),
                 str(v.get("details", ""))),
            )
        con.commit()
        con.close()
        logger.info("SQLite report: %s", path)
        return str(path)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _clean(self, violations: List[dict]) -> List[dict]:
        """Strip non-serialisable values (e.g. frame_snapshot bytes)."""
        result = []
        for v in violations:
            d = {}
            for k, val in v.items():
                if k == "frame_snapshot":
                    continue
                if hasattr(val, "isoformat"):
                    d[k] = val.isoformat()
                else:
                    d[k] = val
            result.append(d)
        return result
