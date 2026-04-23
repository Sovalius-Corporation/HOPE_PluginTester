"""SessionHistoryPanel -- recent session records backed by QSettings."""
from __future__ import annotations

import json
from datetime import datetime
from typing import List

from PySide6.QtCore import QSettings
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

_KEY     = "session_history_v1"
_MAX     = 100
_COLS    = ["Date/Time", "Session", "Video", "Violations", "Duration", "Notes"]


class SessionHistoryPanel(QWidget):
    """Shows a list of recent sessions loaded from QSettings."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._settings = QSettings("HOPEPluginTester", "History")

        hdr = QLabel("SESSION HISTORY")
        hdr.setStyleSheet(
            "color:rgba(255,255,255,0.55);font-size:10px;font-weight:700;"
            "letter-spacing:2px;padding:6px 8px 4px 8px;"
        )
        clear_btn = QPushButton("Clear All")
        clear_btn.setFixedWidth(80)
        clear_btn.clicked.connect(self._on_clear)

        hdr_row = QHBoxLayout()
        hdr_row.addWidget(hdr)
        hdr_row.addStretch()
        hdr_row.addWidget(clear_btn)

        self._table = QTableWidget(0, len(_COLS))
        self._table.setHorizontalHeaderLabels(_COLS)
        self._table.setAlternatingRowColors(True)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.verticalHeader().setVisible(False)
        self._table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self._table.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeMode.Stretch)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addLayout(hdr_row)
        layout.addWidget(self._table)

        self._load()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def add_entry(
        self,
        name: str,
        video: str,
        violations: int,
        duration_sec: float,
        notes: str = "",
    ) -> None:
        entry = {
            "ts":         datetime.now().strftime("%Y-%m-%d %H:%M"),
            "name":       name,
            "video":      video,
            "violations": violations,
            "duration":   round(duration_sec, 1),
            "notes":      notes,
        }
        entries = self._load_raw()
        entries.insert(0, entry)
        entries = entries[:_MAX]
        self._settings.setValue(_KEY, json.dumps(entries))
        self._populate(entries)

    # ------------------------------------------------------------------

    def _load(self) -> None:
        self._populate(self._load_raw())

    def _load_raw(self) -> List[dict]:
        try:
            return json.loads(self._settings.value(_KEY, "[]"))
        except Exception:
            return []

    def _populate(self, entries: List[dict]) -> None:
        self._table.setRowCount(0)
        for e in entries:
            row = self._table.rowCount()
            self._table.insertRow(row)
            dur = e.get("duration", 0)
            dur_str = f"{int(dur // 60)}m {int(dur % 60):02d}s"
            vals = [
                e.get("ts", ""), e.get("name", ""),
                e.get("video", ""), str(e.get("violations", 0)),
                dur_str, e.get("notes", ""),
            ]
            viols = int(e.get("violations", 0))
            for col, val in enumerate(vals):
                item = QTableWidgetItem(val)
                if col == 3 and viols > 0:
                    item.setForeground(QColor(252, 211, 77))
                else:
                    item.setForeground(QColor(200, 210, 230))
                self._table.setItem(row, col, item)

    def _on_clear(self) -> None:
        self._settings.remove(_KEY)
        self._table.setRowCount(0)
