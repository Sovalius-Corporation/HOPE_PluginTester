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
import time
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QSizePolicy,
    QSplitter,
    QStatusBar,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from ui.chart_panel import ChartPanel
from ui.github_panel import GitHubPanel
from ui.plugin_panel import PluginPanel
from ui.scenario_panel import ScenarioPanel
from ui.session_history import SessionHistoryPanel
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


_QSS_LIGHT = """
QMainWindow, QWidget        { background-color: #f1f5f9; color: #0f172a; }
QSplitter::handle           { background-color: rgba(0,0,0,0.1); }
QPlainTextEdit, QTextEdit   { background-color: #ffffff; color: #1e293b; border:1px solid #cbd5e1; }
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox {
    background-color: #ffffff; border: 1px solid #cbd5e1; border-radius:4px; padding:4px 8px; color:#0f172a;
}
QTabBar::tab        { background-color: #e2e8f0; color: #475569; }
QTabBar::tab:selected { background-color: #f1f5f9; color: #0f172a; }
QTableWidget        { background-color: #ffffff; alternate-background-color: #f8fafc; color: #0f172a; }
QHeaderView::section{ background-color: #e2e8f0; color: #475569; }
QTreeWidget         { background-color: #ffffff; color: #0f172a; }
QGroupBox           { border:1px solid #cbd5e1; }
QGroupBox::title    { color: #64748b; }
QStatusBar          { background-color: #e2e8f0; color: #475569; }
QMenuBar            { background-color: #e2e8f0; color: #0f172a; }
QMenu               { background-color: #ffffff; color: #0f172a; border:1px solid #cbd5e1; }
QMenu::item:selected{ background-color: #e0e7ff; }
QScrollBar:vertical { background:#f1f5f9; }
QScrollBar::handle:vertical { background: rgba(0,0,0,0.2); }
"""


class HOPEPluginTester(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("HOPE Plugin Tester")
        self.resize(1400, 860)
        self.setMinimumSize(900, 600)

        QApplication.instance().setStyleSheet(_QSS)

        self._session = None
        self._session_start_time: float = 0.0
        self._dark_theme: bool = True
        self._compare_session = None
        self._hot_reloader = None

        self._build_ui()
        self._build_menu()
        self._build_shortcuts()

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

        # ---- Main body: video(s) | right-column ----
        main_split = QSplitter(Qt.Orientation.Horizontal)

        # Video area: may contain a second panel for side-by-side compare
        self._video_split = QSplitter(Qt.Orientation.Horizontal)
        self._video_panel = VideoPanel()
        self._video_panel_b = VideoPanel()   # second feed (compare mode, hidden by default)
        self._video_panel_b.setVisible(False)
        self._video_split.addWidget(self._video_panel)
        self._video_split.addWidget(self._video_panel_b)
        main_split.addWidget(self._video_split)

        # Right panel: tabbed
        self._right_tabs = QTabWidget()
        self._plugin_panel = PluginPanel()
        self._violations_panel = ViolationsPanel()
        live_widget = QWidget()
        live_split = QSplitter(Qt.Orientation.Vertical)
        live_split.addWidget(self._plugin_panel)
        live_split.addWidget(self._violations_panel)
        live_split.setSizes([180, 400])
        live_layout = QVBoxLayout(live_widget)
        live_layout.setContentsMargins(0, 0, 0, 0)
        live_layout.addWidget(live_split)

        self._chart_panel   = ChartPanel()
        self._history_panel = SessionHistoryPanel()
        self._github_panel  = GitHubPanel()

        self._right_tabs.addTab(live_widget,          "Live")
        self._right_tabs.addTab(self._chart_panel,    "Chart")
        self._right_tabs.addTab(self._history_panel,  "History")
        self._right_tabs.addTab(self._github_panel,   "GitHub")

        main_split.addWidget(self._right_tabs)
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
        self._video_panel.fullscreen_requested.connect(self._toggle_fullscreen)
        self._github_panel.plugins_downloaded.connect(
            lambda d: self._scenario_panel._qc_plugins_dir.setText(d)
        )

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

        self._record_btn = QPushButton("⏺ Record")
        self._record_btn.setCheckable(True)
        self._record_btn.setEnabled(False)
        self._record_btn.setToolTip("Record annotated video to file")
        self._record_btn.clicked.connect(self._on_record_toggle)

        layout.addWidget(title)
        layout.addWidget(self._pause_btn)
        layout.addWidget(self._step_btn)
        layout.addWidget(sep)
        layout.addWidget(self._lanes_btn)
        layout.addWidget(self._tracks_btn)
        layout.addWidget(self._labels_btn)
        layout.addStretch()
        layout.addWidget(self._record_btn)
        layout.addWidget(clear_btn)
        return bar

    def _build_menu(self) -> None:
        mb = self.menuBar()

        # File
        fm = mb.addMenu("&File")
        act_export = fm.addAction("Export Violations…")
        act_export.setShortcut(QKeySequence("Ctrl+E"))
        act_export.triggered.connect(self._violations_panel._on_export)
        fm.addSeparator()
        act_quit = fm.addAction("Quit")
        act_quit.setShortcut(QKeySequence("Ctrl+Q"))
        act_quit.triggered.connect(self.close)

        # Session
        sm = mb.addMenu("&Session")
        act_batch = sm.addAction("Batch Processing…")
        act_batch.triggered.connect(self._on_batch)
        sm.addSeparator()
        act_compare = sm.addAction("Side-by-side Compare…")
        act_compare.triggered.connect(self._on_compare)
        act_compare_off = sm.addAction("Close Compare")
        act_compare_off.triggered.connect(self._on_compare_close)

        # View
        vm = mb.addMenu("&View")
        act_fs = vm.addAction("Full Screen")
        act_fs.setShortcut(QKeySequence("F11"))
        act_fs.triggered.connect(self._toggle_fullscreen)
        act_theme = vm.addAction("Toggle Dark / Light Theme")
        act_theme.triggered.connect(self._toggle_theme)
        vm.addSeparator()
        act_chart = vm.addAction("Chart Tab")
        act_chart.triggered.connect(lambda: self._right_tabs.setCurrentWidget(self._chart_panel))
        act_hist = vm.addAction("History Tab")
        act_hist.triggered.connect(lambda: self._right_tabs.setCurrentWidget(self._history_panel))
        act_gh = vm.addAction("GitHub Tab")
        act_gh.triggered.connect(lambda: self._right_tabs.setCurrentWidget(self._github_panel))

        # Plugins
        pm = mb.addMenu("&Plugins")
        act_scaffold = pm.addAction("New Plugin Scaffold…")
        act_scaffold.triggered.connect(self._on_scaffold)
        pm.addSeparator()
        act_clear_gt = pm.addAction("Clear GT Labels")
        act_clear_gt.triggered.connect(self._video_panel.clear_gt_labels)

    def _build_shortcuts(self) -> None:
        QShortcut(QKeySequence("Space"), self).activated.connect(self._on_pause)
        QShortcut(QKeySequence(Qt.Key.Key_Right), self).activated.connect(self._on_step)
        QShortcut(QKeySequence("R"), self).activated.connect(
            lambda: self._scenario_panel._on_run()
        )
        QShortcut(QKeySequence("F11"), self).activated.connect(self._toggle_fullscreen)
        QShortcut(QKeySequence(Qt.Key.Key_Escape), self).activated.connect(
            lambda: self.showNormal() if self.isFullScreen() else None
        )

    # ------------------------------------------------------------------
    # Session management
    # ------------------------------------------------------------------

    def _on_run(self, scenario) -> None:
        from core.hot_reloader import HotReloader
        from core.session import TestSession

        if self._session and self._session.isRunning():
            return

        self._violations_panel.clear()
        self._plugin_panel.clear()
        self._plugin_panel.set_plugins(scenario.plugins)
        self._video_panel.set_scenario(scenario)
        self._video_panel.clear()
        self._chart_panel.start_session()
        self._session_start_time = time.monotonic()

        self._session = TestSession(scenario)
        self._session.frame_ready.connect(
            lambda frame, tracks, viols, fidx:
                self._video_panel.update_frame(frame, tracks, viols, fidx)
        )
        self._session.violation_detected.connect(self._violations_panel.add_violation)
        self._session.violation_detected.connect(self._plugin_panel.on_violation)
        self._session.violation_detected.connect(self._chart_panel.add_violation)
        self._session.stats_updated.connect(self._on_stats)
        self._session.session_error.connect(self._on_error)
        self._session.finished.connect(self._on_finished)
        self._session.paused_changed.connect(self._on_paused_changed)
        self._violations_panel.frame_requested.connect(self._video_panel.show_snapshot)

        # Hot reload — watch the plugins dir if running standalone
        plugins_dir = str(getattr(scenario, "plugins_dir", "")).strip()
        if plugins_dir:
            self._hot_reloader = HotReloader(parent=self)
            self._hot_reloader.plugin_changed.connect(
                self._session.request_plugin_reload
            )
            self._hot_reloader.watch(plugins_dir)
        else:
            self._hot_reloader = None

        self._session.start()

        self._pause_btn.setEnabled(True)
        self._step_btn.setEnabled(False)
        self._record_btn.setEnabled(True)

        self._scenario_panel.set_running(True)
        self._status_label.setText(f"Running — {scenario.name}")
        logger.info("Session started: %s", scenario.name)

    def _on_stop(self) -> None:
        if self._session:
            self._session.stop()
        if self._hot_reloader:
            self._hot_reloader.stop()
            self._hot_reloader = None
        self._pause_btn.setEnabled(False)
        self._pause_btn.setText("⏸  Pause")
        self._step_btn.setEnabled(False)
        self._record_btn.setEnabled(False)

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
        self._record_btn.setEnabled(False)
        self._record_btn.setChecked(False)
        self._chart_panel.stop_session()
        if self._hot_reloader:
            self._hot_reloader.stop()
            self._hot_reloader = None

        # Add to session history
        scn = self._session.scenario
        duration = time.monotonic() - self._session_start_time
        n_viols  = self._violations_panel._table.rowCount() if hasattr(self._violations_panel, "_table") else 0
        vid = str(getattr(scn, "video_path", ""))
        self._history_panel.add_entry(
            name=scn.name,
            video=vid,
            violations=n_viols,
            duration_sec=duration,
        )
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
        self._video_panel.set_paused(paused)

    def _on_clear(self) -> None:
        self._violations_panel.clear()
        self._plugin_panel.clear()
        self._video_panel.clear()
        self._fps_label.setText("")
        self._status_label.setText("Ready")

    def _on_record_toggle(self, checked: bool) -> None:
        if not self._session:
            self._record_btn.setChecked(False)
            return
        if checked:
            path, _ = QFileDialog.getSaveFileName(
                self, "Save Annotated Video", "recording.mp4",
                "MP4 (*.mp4);;AVI (*.avi);;All files (*)"
            )
            if not path:
                self._record_btn.setChecked(False)
                return
            self._session.start_recording(path)
            self._status_label.setText(f"Recording → {path}")
        else:
            self._session.stop_recording()
            self._status_label.setText("Recording saved.")

    # ------------------------------------------------------------------
    # Fullscreen
    # ------------------------------------------------------------------

    def _toggle_fullscreen(self) -> None:
        if self.isFullScreen():
            self.showNormal()
        else:
            self.showFullScreen()

    # ------------------------------------------------------------------
    # Theme toggle
    # ------------------------------------------------------------------

    def _toggle_theme(self) -> None:
        self._dark_theme = not self._dark_theme
        QApplication.instance().setStyleSheet(
            _QSS if self._dark_theme else _QSS_LIGHT
        )

    # ------------------------------------------------------------------
    # Compare mode
    # ------------------------------------------------------------------

    def _on_compare(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Open second video for compare", "",
            "Video files (*.mp4 *.avi *.mkv *.mov *.wmv *.ts *.m4v);;All files (*)"
        )
        if not path or not self._session:
            return
        from core.session import TestSession
        import copy
        scn_b = copy.copy(self._session.scenario)
        scn_b.video_path = path
        self._compare_session = TestSession(scn_b)
        self._compare_session.frame_ready.connect(
            lambda frame, tracks, viols, fidx:
                self._video_panel_b.update_frame(frame, tracks, viols, fidx)
        )
        self._compare_session.start()
        self._video_panel_b.setVisible(True)
        self._status_label.setText("Compare mode active")

    def _on_compare_close(self) -> None:
        if self._compare_session:
            self._compare_session.stop()
            self._compare_session = None
        self._video_panel_b.setVisible(False)
        self._video_panel_b.clear()

    # ------------------------------------------------------------------
    # Batch & Scaffold
    # ------------------------------------------------------------------

    def _on_batch(self) -> None:
        from ui.batch_dialog import BatchDialog
        scn = self._scenario_panel.get_scenario()
        if scn is None:
            self._scenario_panel.log("[BATCH] Run the scenario first to load it, then open Batch.")
            return
        dlg = BatchDialog(scn, parent=self)
        dlg.exec()

    def _on_scaffold(self) -> None:
        from ui.scaffold_dialog import ScaffoldDialog
        plugins_dir = getattr(self._scenario_panel, "_qc_plugins_dir", None)
        default_dir = plugins_dir.text() if plugins_dir else ""
        dlg = ScaffoldDialog(default_dir=default_dir, parent=self)
        dlg.plugin_created.connect(
            lambda path: self._scenario_panel.log(f"[SCAFFOLD] Created: {path}")
        )
        dlg.exec()

    # ------------------------------------------------------------------

    def closeEvent(self, event) -> None:
        if self._session and self._session.isRunning():
            self._session.stop()
            self._session.wait(3000)
        if self._compare_session and self._compare_session.isRunning():
            self._compare_session.stop()
            self._compare_session.wait(2000)
        if getattr(self, "_hot_reloader", None):
            self._hot_reloader.stop()
        super().closeEvent(event)
