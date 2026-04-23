"""ViolationsPanel — live table of all violations detected in the current run."""
from __future__ import annotations

import csv
from datetime import datetime
from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

_SEVERITY_COLORS = {
    "critical": QColor(239, 68,  68,  220),
    "high":     QColor(239, 68,  68,  160),
    "medium":   QColor(245, 158, 11,  160),
    "low":      QColor(34,  197, 94,  140),
}

_COLS = ["Time", "Type", "Severity", "Track", "Plate", "Speed (mph)", "Details"]

# ItemDataRole for storing the JPEG snapshot bytes on row 0, col 0
_ROLE_SNAPSHOT = Qt.ItemDataRole.UserRole + 1


class ViolationsPanel(QWidget):
    # Emitted when a row with a snapshot is clicked; payload = JPEG bytes
    frame_requested = Signal(object)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)

        # --- Header row ---
        hdr = QLabel("VIOLATIONS")
        hdr.setStyleSheet(
            "color: rgba(255,255,255,0.55); font-size: 10px; font-weight: 700;"
            "letter-spacing: 2px; padding: 6px 8px 4px 8px; background: transparent;"
        )

        clear_btn = QPushButton("Clear")
        clear_btn.setFixedWidth(60)
        clear_btn.clicked.connect(self.clear)

        export_btn = QPushButton("Export…")
        export_btn.setFixedWidth(70)
        export_btn.setToolTip("Export violations table to CSV")
        export_btn.clicked.connect(self._on_export)

        hdr_row = QHBoxLayout()
        hdr_row.addWidget(hdr)
        hdr_row.addStretch()
        hdr_row.addWidget(export_btn)
        hdr_row.addWidget(clear_btn)

        # --- Table ---
        self._table = QTableWidget(0, len(_COLS))
        self._table.setHorizontalHeaderLabels(_COLS)
        self._table.setAlternatingRowColors(True)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.verticalHeader().setVisible(False)
        self._table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self._table.horizontalHeader().setSectionResizeMode(6, QHeaderView.ResizeMode.Stretch)
        self._table.setMinimumHeight(100)
        self._table.cellClicked.connect(self._on_cell_clicked)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addLayout(hdr_row)
        layout.addWidget(self._table)

    # ------------------------------------------------------------------

    def add_violation(self, violation: dict) -> None:
        ts = datetime.now().strftime("%H:%M:%S")
        vtype    = str(violation.get("type", "unknown"))
        severity = str(violation.get("severity", "medium")).lower()
        track_id = str(violation.get("track_id", ""))
        plate    = str(violation.get("license_plate") or "")
        speed    = violation.get("max_speed_mph") or violation.get("speed_mph") or ""
        speed    = f"{speed:.1f}" if isinstance(speed, float) else str(speed)
        details  = self._build_details(violation)

        row = self._table.rowCount()
        self._table.insertRow(0)  # insert at top for newest-first

        values = [ts, vtype, severity, track_id, plate, speed, details]
        col_color = _SEVERITY_COLORS.get(severity, QColor(200, 200, 200, 160))

        for col, val in enumerate(values):
            item = QTableWidgetItem(val)
            item.setForeground(col_color if col in (1, 2) else QColor(220, 220, 230))
            self._table.setItem(0, col, item)

        # Store the JPEG snapshot bytes on the first cell for click-to-view
        snap = violation.get("frame_snapshot")
        if snap is not None:
            first_item = self._table.item(0, 0)
            if first_item is not None:
                first_item.setData(_ROLE_SNAPSHOT, snap)

        # Keep at most 500 rows
        if self._table.rowCount() > 500:
            self._table.removeRow(self._table.rowCount() - 1)

    def clear(self) -> None:
        self._table.setRowCount(0)

    # ------------------------------------------------------------------
    # Event handlers
    # ------------------------------------------------------------------

    def _on_cell_clicked(self, row: int, col: int) -> None:
        """Click any cell in a violation row to show its snapshot in the video panel."""
        item = self._table.item(row, 0)
        if item is None:
            return
        snap = item.data(_ROLE_SNAPSHOT)
        if snap is not None:
            self.frame_requested.emit(snap)

    def _on_export(self) -> None:
        """Export the current violations table to a CSV file."""
        path, _ = QFileDialog.getSaveFileName(
            self, "Export Violations", "violations.csv",
            "CSV files (*.csv);;All files (*)",
        )
        if not path:
            return
        with open(path, "w", newline="", encoding="utf-8") as fh:
            writer = csv.writer(fh)
            writer.writerow(_COLS)
            for row in range(self._table.rowCount()):
                writer.writerow([
                    (self._table.item(row, c).text()
                     if self._table.item(row, c) else "")
                    for c in range(len(_COLS))
                ])

    # ------------------------------------------------------------------

    @staticmethod
    def _build_details(v: dict) -> str:
        parts = []
        if "over_limit_mph" in v:
            parts.append(f"+{v['over_limit_mph']:.1f}mph over")
        if "speed_limit_mph" in v:
            parts.append(f"limit {v['speed_limit_mph']}mph")
        if "duration_seconds" in v:
            parts.append(f"{v['duration_seconds']:.1f}s")
        if "location" in v and v["location"]:
            parts.append(v["location"])
        return "  |  ".join(parts) if parts else ""
