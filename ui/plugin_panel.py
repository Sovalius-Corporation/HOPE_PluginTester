"""PluginPanel — shows loaded plugins with status and per-plugin violation counts."""
from __future__ import annotations

from typing import Dict, List, Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

_STATUS_LOADED  = "LOADED"
_STATUS_FAILED  = "FAILED"
_STATUS_IDLE    = "IDLE"


class PluginPanel(QWidget):
    """Displays loaded plugins, their status, and live violation counts."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._counts: Dict[str, int] = {}

        # --- Header ---
        hdr = QLabel("PLUGINS")
        hdr.setStyleSheet(
            "color: rgba(255,255,255,0.55); font-size: 10px; font-weight: 700;"
            "letter-spacing: 2px; padding: 6px 8px 4px 8px; background: transparent;"
        )

        # --- Tree ---
        self._tree = QTreeWidget()
        self._tree.setColumnCount(4)
        self._tree.setHeaderLabels(["Plugin", "Status", "Violations", "ms/f"])
        self._tree.setAlternatingRowColors(True)
        self._tree.setRootIsDecorated(False)
        self._tree.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self._tree.header().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self._tree.header().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self._tree.header().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self._tree.setMinimumHeight(100)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(hdr)
        layout.addWidget(self._tree)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_plugins(self, plugin_ids: List[str]) -> None:
        """Populate the tree with *plugin_ids* (called after session starts)."""
        self._tree.clear()
        self._counts = {pid: 0 for pid in plugin_ids}
        for pid in plugin_ids:
            item = QTreeWidgetItem([pid, _STATUS_LOADED, "0", "—"])
            item.setForeground(1, QColor(134, 239, 172))   # green
            item.setTextAlignment(2, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            item.setTextAlignment(3, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self._tree.addTopLevelItem(item)

    def mark_failed(self, plugin_id: str) -> None:
        for i in range(self._tree.topLevelItemCount()):
            item = self._tree.topLevelItem(i)
            if item.text(0) == plugin_id:
                item.setText(1, _STATUS_FAILED)
                item.setForeground(1, QColor(252, 165, 165))
                break

    def on_violation(self, violation: dict) -> None:
        pid = violation.get("plugin_id", "")
        if not pid:
            # Try to match by type to a plugin name
            pid = violation.get("type", "")
        self._counts[pid] = self._counts.get(pid, 0) + 1
        for i in range(self._tree.topLevelItemCount()):
            item = self._tree.topLevelItem(i)
            if item.text(0) == pid or pid.startswith(item.text(0)):
                item.setText(2, str(self._counts[pid]))
                item.setForeground(2, QColor(252, 211, 77))   # amber
                break

    def clear(self) -> None:
        self._counts.clear()
        for i in range(self._tree.topLevelItemCount()):
            item = self._tree.topLevelItem(i)
            item.setText(2, "0")
            item.setText(3, "—")
            item.setForeground(2, QColor(200, 200, 200))

    def update_latency(self, latencies: dict) -> None:
        """Update the ms/f column from a ``{plugin_id: ms}`` dict."""
        for i in range(self._tree.topLevelItemCount()):
            item = self._tree.topLevelItem(i)
            pid = item.text(0)
            if pid in latencies:
                item.setText(3, f"{latencies[pid]:.1f}")
                item.setForeground(3, QColor(148, 163, 184))
