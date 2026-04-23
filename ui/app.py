"""HOPEPluginTester — main application window.

Layout
------
┌─[Open Video]─[Load Script]─[Save Script]──────[Run ▶]─[Stop ■]─[Clear]─┐
├────────────────────────────┬─────────────────────────────────────────────┤
│ VideoPanel (left)          │ right: QSplitter(vertical)                  │
│                            │  ┌── PluginPanel (top)  ─────────────────┐  │
│                            │  └── ViolationsPanel (bottom) ───────────┘  │
├────────────────────────────┴─────────────────────────────────────────────┤
│ ScenarioPanel (bottom)                                                   │
└──────────────────────────────────────────────────────────────────────────┘
"""
from __future__ import annotations

import logging
from typing import Optional

from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QSizePolicy,
    QSplitter,
    QStatusBar,
    QVBoxLayout,
    QWidget,
)

from ui.plugin_panel import PluginPanel
from ui.scenario_panel import ScenarioPanel
from ui.video_panel import VideoPanel
from ui.violations_panel import ViolationsPanel

logger = logging.getLogger(__name__)

_QSS = """
/* ---- Global ---- */
QMainWindow, QWidget        { background-color: #0a0f1a; color: #e2e8f0; }
QSplitter::handle           { background-color: rgba(255,255,255,0.07); }
QSplitter::handle:horizontal{ width:  4px; }
QSplitter::handle:vertical  { height: 4px; }

/* ---- Buttons ---- */
QPushButton {
    background-color: #1e293b;
    border: 1px solid rgba(255,255,255,0.10);
    border-radius: 6px;
    padding: 6px 14px;
    color: #e2e8f0;
}
QPushButton:hover   { background-color: #334155; border-color: rgba(139,92,246,0.5); }
QPushButton:pressed { background-color: #141926; }
QPushButton:disabled{ color: rgba(255,255,255,0.3); background-color: rgba(30,41,59,0.4); }
QPushButton#primary {
    background: qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #6366f1,stop:1 #8b5cf6);
    border: none;
    font-weight: 700;
}
QPushButton#primary:hover   { background: qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #7073f4,stop:1 #9e6ff9); }
QPushButton#primary:disabled{ background: rgba(99,102,241,0.3); }

/* ---- Inputs ---- */
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox {
    background-color: #0d1422;
    border: 1px solid rgba(255,255,255,0.10);
    border-radius: 4px;
    padding: 4px 8px;
    color: #e2e8f0;
}
QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus {
    border-color: rgba(139,92,246,0.6);
}

/* ---- Text areas ---- */
QPlainTextEdit, QTextEdit {
    background-color: #060c18;
    border: 1px solid rgba(255,255,255,0.07);
    border-radius: 6px;
    font-family: Consolas, "Courier New", monospace;
    color: #c4b5fd;
}

/* ---- Tabs ---- */
QTabWidget::pane {
    border: 1px solid rgba(255,255,255,0.08);
    background-color: #0a0f1a;
}
QTabBar::tab {
    background-color: #0d1422;
    padding: 5px 14px;
    color: rgba(255,255,255,0.6);
    border-top-left-radius: 4px;
    border-top-right-radius: 4px;
    margin-right: 2px;
}
QTabBar::tab:selected {
    background-color: #0a0f1a;
    color: #ffffff;
    border: 1px solid rgba(139,92,246,0.4);
    border-bottom: 1px solid #0a0f1a;
}
QTabBar::tab:hover:!selected { background-color: #111827; color: #ffffff; }

/* ---- Tables ---- */
QTableWidget {
    background-color: #0d1422;
    border: 1px solid rgba(255,255,255,0.07);
    alternate-background-color: #111827;
    gridline-color: rgba(255,255,255,0.05);
    color: #e2e8f0;
    outline: none;
}
QTableWidget::item:selected { background-color: rgba(99,102,241,0.25); }
QHeaderView::section {
    background-color: #1e293b;
    color: rgba(255,255,255,0.6);
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 1px;
    border: none;
    border-right: 1px solid rgba(255,255,255,0.06);
    padding: 4px 8px;
}

/* ---- Tree ---- */
QTreeWidget {
    background-color: #0d1422;
    border: 1px solid rgba(255,255,255,0.07);
    alternate-background-color: #111827;
    color: #e2e8f0;
    outline: none;
}
QTreeWidget::item:selected { background-color: rgba(99,102,241,0.25); }

/* ---- GroupBox ---- */
QGroupBox {
    border: 1px solid rgba(255,255,255,0.08);
    border-radius: 8px;
    margin-top: 12px;
    padding: 12px 8px 8px 8px;
    color: rgba(255,255,255,0.88);
}
QGroupBox::title {
    color: rgba(255,255,255,0.55);
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 1px;
    subcontrol-origin: margin;
    subcontrol-position: top left;
    padding: 0 6px;
}

/* ---- Scrollbars ---- */
QScrollBar:vertical { background: transparent; width: 8px; }
QScrollBar::handle:vertical {
    background: rgba(255,255,255,0.15);
    border-radius: 4px;
    min-height: 20px;
}
QScrollBar::handle:vertical:hover { background: rgba(139,92,246,0.4); }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }

QScrollBar:horizontal { background: transparent; height: 8px; }
QScrollBar::handle:horizontal {
    background: rgba(255,255,255,0.15);
    border-radius: 4px;
    min-width: 20px;
}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0; }

/* ---- Status bar ---- */
QStatusBar { background-color: #0c0c0c; color: rgba(255,255,255,0.6); font-size: 10px; }
"""


class HOPEPluginTester(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("HOPE Plugin Tester")
        self.resize(1400, 860)
        self.setMinimumSize(900, 600)

        QApplication.instance().setStyleSheet(_QSS)

        self._session = None

        self._build_ui()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        root_layout = QVBoxLayout(central)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        # ---- Top toolbar ----
        root_layout.addWidget(self._build_toolbar())

        # ---- Main body: video | right-column ----
        main_split = QSplitter(Qt.Orientation.Horizontal)

        self._video_panel = VideoPanel()
        main_split.addWidget(self._video_panel)

        right_split = QSplitter(Qt.Orientation.Vertical)
        self._plugin_panel = PluginPanel()
        self._violations_panel = ViolationsPanel()
        right_split.addWidget(self._plugin_panel)
        right_split.addWidget(self._violations_panel)
        right_split.setSizes([180, 400])

        main_split.addWidget(right_split)
        main_split.setSizes([860, 540])
        root_layout.addWidget(main_split, stretch=1)

        # ---- Scenario panel (bottom) ----
        self._scenario_panel = ScenarioPanel()
        root_layout.addWidget(self._scenario_panel)

        # ---- Status bar ----
        self._status = QStatusBar()
        self.setStatusBar(self._status)
        self._status_label = QLabel("Ready")
        self._status.addWidget(self._status_label)
        self._fps_label = QLabel("")
        self._status.addPermanentWidget(self._fps_label)

        # ---- Wire signals ----
        self._scenario_panel.run_requested.connect(self._on_run)
        self._scenario_panel.stop_requested.connect(self._on_stop)

    def _build_toolbar(self) -> QWidget:
        bar = QWidget()
        bar.setFixedHeight(44)
        bar.setStyleSheet("background-color: #0c0c14; border-bottom: 1px solid #141414;")
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(10, 4, 10, 4)
        layout.setSpacing(6)

        title = QLabel("HOPE Plugin Tester")
        title.setStyleSheet("font-weight: 700; font-size: 13px; color: #c4b5fd; padding-right: 16px;")

        # Pause / Step
        self._pause_btn = QPushButton("⏸  Pause")
        self._pause_btn.setFixedWidth(90)
        self._pause_btn.setToolTip("Pause / Resume the running session")
        self._pause_btn.setEnabled(False)
        self._pause_btn.clicked.connect(self._on_pause)

        self._step_btn = QPushButton("⏭  Step")
        self._step_btn.setFixedWidth(80)
        self._step_btn.setToolTip("Advance one frame while paused")
        self._step_btn.setEnabled(False)
        self._step_btn.clicked.connect(self._on_step)

        # Overlay toggles
        sep = QLabel("|")
        sep.setStyleSheet("color: rgba(255,255,255,0.2); padding: 0 4px;")

        self._lanes_btn  = QPushButton("Lanes")
        self._tracks_btn = QPushButton("Boxes")
        self._labels_btn = QPushButton("Labels")
        for btn in (self._lanes_btn, self._tracks_btn, self._labels_btn):
            btn.setCheckable(True)
            btn.setChecked(True)
            btn.setFixedWidth(60)
        self._lanes_btn.clicked.connect(
            lambda: self._video_panel.toggle_lanes())
        self._tracks_btn.clicked.connect(
            lambda: self._video_panel.toggle_tracks())
        self._labels_btn.clicked.connect(
            lambda: self._video_panel.toggle_labels())

        clear_btn = QPushButton("Clear Log")
        clear_btn.clicked.connect(self._on_clear)

        layout.addWidget(title)
        layout.addWidget(self._pause_btn)
        layout.addWidget(self._step_btn)
        layout.addWidget(sep)
        layout.addWidget(self._lanes_btn)
        layout.addWidget(self._tracks_btn)
        layout.addWidget(self._labels_btn)
        layout.addStretch()
        layout.addWidget(clear_btn)
        return bar

    # ------------------------------------------------------------------
    # Session management
    # ------------------------------------------------------------------

    def _on_run(self, scenario) -> None:
        from core.session import TestSession

        if self._session and self._session.isRunning():
            return

        self._violations_panel.clear()
        self._plugin_panel.clear()
        self._plugin_panel.set_plugins(scenario.plugins)
        self._video_panel.set_scenario(scenario)
        self._video_panel.clear()

        self._session = TestSession(scenario)
        self._session.frame_ready.connect(self._video_panel.update_frame)
        self._session.violation_detected.connect(self._violations_panel.add_violation)
        self._session.violation_detected.connect(self._plugin_panel.on_violation)
        self._session.stats_updated.connect(self._on_stats)
        self._session.session_error.connect(self._on_error)
        self._session.finished.connect(self._on_finished)
        self._session.paused_changed.connect(self._on_paused_changed)
        self._violations_panel.frame_requested.connect(self._video_panel.show_snapshot)
        self._session.start()

        self._pause_btn.setEnabled(True)
        self._step_btn.setEnabled(False)

        self._scenario_panel.set_running(True)
        self._status_label.setText(f"Running — {scenario.name}")
        logger.info("Session started: %s", scenario.name)

    def _on_stop(self) -> None:
        if self._session:
            self._session.stop()
        self._pause_btn.setEnabled(False)
        self._pause_btn.setText("⏸  Pause")
        self._step_btn.setEnabled(False)

    def _on_stats(self, stats: dict) -> None:
        fps   = stats.get("processing_fps", 0)
        frame = stats.get("frame_index", 0)
        total = stats.get("total_violations", 0)
        trk   = stats.get("active_tracks", 0)
        self._fps_label.setText(
            f"frame {frame}  |  {fps:.1f} fps  |  tracks {trk}  |  violations {total}"
        )
        latencies = stats.get("plugin_latency_ms", {})
        if latencies:
            self._plugin_panel.update_latency(latencies)

    def _on_error(self, msg: str) -> None:
        self._scenario_panel.log(f"[ERROR] {msg}")
        self._scenario_panel.set_running(False)
        self._status_label.setText("Error — see Output tab")
        self._pause_btn.setEnabled(False)
        self._step_btn.setEnabled(False)

    def _on_finished(self) -> None:
        self._scenario_panel.set_running(False)
        self._status_label.setText("Finished")
        self._scenario_panel.log("Session finished.")
        self._pause_btn.setEnabled(False)
        self._pause_btn.setText("⏸  Pause")
        self._step_btn.setEnabled(False)
        logger.info("Session finished.")

    # ------------------------------------------------------------------
    # Pause / Step handlers
    # ------------------------------------------------------------------

    def _on_pause(self) -> None:
        if not (self._session and self._session.isRunning()):
            return
        if self._session._is_paused:
            self._session.resume()
        else:
            self._session.pause()

    def _on_step(self) -> None:
        if self._session:
            self._session.step()

    def _on_paused_changed(self, paused: bool) -> None:
        self._pause_btn.setText("▶  Resume" if paused else "⏸  Pause")
        self._step_btn.setEnabled(paused)

    def _on_clear(self) -> None:
        self._violations_panel.clear()
        self._plugin_panel.clear()
        self._video_panel.clear()
        self._fps_label.setText("")
        self._status_label.setText("Ready")

    # ------------------------------------------------------------------

    def closeEvent(self, event) -> None:
        if self._session and self._session.isRunning():
            self._session.stop()
            self._session.wait(3000)
        super().closeEvent(event)
