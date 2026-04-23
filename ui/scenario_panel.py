"""ScenarioPanel — script editor + output log, wired to Run/Stop controls.

Tabs:
  Script    — Python editor where user writes/pastes a Scenario script.
              Click Run to exec() it and extract the Scenario object.
  Quick Config — Form-based shortcut for the most common fields.
  Output    — Run log + assertion results.
"""
from __future__ import annotations

import os
import sys
import traceback
from typing import Optional

from PySide6.QtCore import Signal, Qt, QSettings
from PySide6.QtGui import QFont, QColor
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QDoubleSpinBox,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from scenarios.base import Camera, Lane, Scenario

_EXAMPLE_SCRIPT = '''\
# HOPE Plugin Tester — scenario script
# Edit the paths below and click Run ▶

from scenarios.base import Scenario, Camera, Lane, ViolationAssertion

s = Scenario("my_test")

# --- Paths ---
# svg_hope_root is OPTIONAL: only needed if you are running SVG_HOPE violation plugins.
# Leave it out (or blank) to run detection + tracking only, or point plugins_dir
# at a folder of standalone .py plugins that don\'t require SVG_HOPE.
s.svg_hope_root = r"D:\\Projects\\SVG_HOPE"   # optional
# s.plugins_dir = r"D:\\my_plugins"           # alternative: standalone plugins folder

s.video_path = r"D:\\videos\\test.mp4"
s.model_path = r"D:\\Projects\\SVG_HOPE\\models\\yolov8n.onnx"

# --- Inference device ---
# "auto"  = CUDA > DirectML > CPU  (default)
# "dml"   = AMD Radeon / Intel via DirectML  (pip install onnxruntime-directml)
# "cuda"  = NVIDIA CUDA              (pip install onnxruntime-gpu)
# "cpu"   = always available
s.device = "auto"

s.plugins = ["speeding"]
s.plugin_config = {
    "speeding": {
        "tolerance_mph":      0,
        "min_duration_sec":   1.0,
        "min_frames_tracked": 5,
    }
}

s.camera = Camera(
    name="cam1",
    speed_limit_mph=5,         # low limit to guarantee detections
    pixels_per_meter=8.5,
)

# Cover full frame with one lane
s.lanes = [
    Lane(
        lane_id=0,
        boundaries=[(0, 0), (1280, 0), (1280, 720), (0, 720)],
        speed_limit_mph=5,
    )
]

s.assertions = [ViolationAssertion("speeding", min_count=1)]

# The UI will pick up \'s\' automatically.
'''


class ScenarioPanel(QWidget):
    """Bottom panel: script editor + quick-config form + output log."""

    run_requested  = Signal(object)   # Scenario instance
    stop_requested = Signal()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setMaximumHeight(360)
        self._current_scenario: Optional[Scenario] = None

        # ---- Toolbar ----
        self._run_btn  = QPushButton("▶  Run")
        self._run_btn.setObjectName("primary")
        self._run_btn.setFixedWidth(90)
        self._stop_btn = QPushButton("■  Stop")
        self._stop_btn.setFixedWidth(90)
        self._stop_btn.setEnabled(False)
        self._load_btn = QPushButton("Open…")
        self._load_btn.setFixedWidth(80)
        self._save_btn = QPushButton("Save…")
        self._save_btn.setFixedWidth(80)

        toolbar = QHBoxLayout()
        toolbar.setSpacing(6)
        toolbar.addWidget(self._load_btn)
        toolbar.addWidget(self._save_btn)
        toolbar.addStretch()
        toolbar.addWidget(self._run_btn)
        toolbar.addWidget(self._stop_btn)

        # ---- Script tab ----
        self._editor = QPlainTextEdit()
        self._editor.setFont(QFont("Consolas", 9))
        self._editor.setPlainText(_EXAMPLE_SCRIPT)

        script_tab = QWidget()
        sl = QVBoxLayout(script_tab)
        sl.setContentsMargins(4, 4, 4, 4)
        sl.addWidget(self._editor)

        # ---- Quick Config tab ----
        qc_tab = self._build_quick_config()

        # ---- Output tab ----
        self._output = QPlainTextEdit()
        self._output.setReadOnly(True)
        self._output.setFont(QFont("Consolas", 8))
        self._output.setStyleSheet("background:#060c18; color:#c4b5fd;")

        out_tab = QWidget()
        ol = QVBoxLayout(out_tab)
        ol.setContentsMargins(4, 4, 4, 4)
        ol.addWidget(self._output)

        # ---- Tabs ----
        self._tabs = QTabWidget()
        self._tabs.addTab(script_tab, "Script")
        self._tabs.addTab(qc_tab,     "Quick Config")
        self._tabs.addTab(out_tab,    "Output")

        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(4, 4, 4, 4)
        root_layout.setSpacing(4)
        root_layout.addLayout(toolbar)
        root_layout.addWidget(self._tabs)

        # ---- Wire ----
        self._run_btn.clicked.connect(self._on_run)
        self._stop_btn.clicked.connect(self._on_stop)
        self._load_btn.clicked.connect(self._on_load)
        self._save_btn.clicked.connect(self._on_save)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_scenario(self) -> Optional[Scenario]:
        return self._current_scenario

    def set_running(self, running: bool) -> None:
        self._run_btn.setEnabled(not running)
        self._stop_btn.setEnabled(running)

    def log(self, text: str) -> None:
        self._output.appendPlainText(text)
        self._tabs.setCurrentIndex(2)   # switch to Output tab

    def log_result(self, result) -> None:
        self._output.appendPlainText("\n" + "=" * 60)
        self._output.appendPlainText(result.summary())
        self._output.appendPlainText("=" * 60 + "\n")
        self._tabs.setCurrentIndex(2)

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------

    def _on_run(self) -> None:
        scenario = self._extract_scenario()
        if scenario is None:
            return
        self._current_scenario = scenario
        self.run_requested.emit(scenario)

    def _on_stop(self) -> None:
        self.stop_requested.emit()

    def _on_load(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Open Scenario Script", "", "Python files (*.py);;All files (*)"
        )
        if path:
            with open(path, "r", encoding="utf-8") as f:
                self._editor.setPlainText(f.read())

    def _on_save(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "Save Scenario Script", "scenario.py", "Python files (*.py)"
        )
        if path:
            with open(path, "w", encoding="utf-8") as f:
                f.write(self._editor.toPlainText())

    # ------------------------------------------------------------------
    # Script execution
    # ------------------------------------------------------------------

    def _extract_scenario(self) -> Optional[Scenario]:
        code = self._editor.toPlainText()
        # Add tester root to sys.path so ``from scenarios.base import`` works
        tester_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        if tester_root not in sys.path:
            sys.path.insert(0, tester_root)

        namespace: dict = {}
        try:
            exec(compile(code, "<scenario>", "exec"), namespace)  # noqa: S102
        except Exception:
            err = traceback.format_exc()
            self._output.appendPlainText("[ERROR] Script execution failed:\n" + err)
            self._tabs.setCurrentIndex(2)
            return None

        # Look for a Scenario instance: first check 's', then 'scenario', then scan
        for key in ("s", "scenario", "scn"):
            val = namespace.get(key)
            if isinstance(val, Scenario):
                return val
        for val in namespace.values():
            if isinstance(val, Scenario):
                return val

        self._output.appendPlainText(
            "[ERROR] No Scenario object found in script.\n"
            "        Assign one to a variable named  s  or  scenario."
        )
        self._tabs.setCurrentIndex(2)
        return None

    # ------------------------------------------------------------------
    # Quick Config tab
    # ------------------------------------------------------------------

    # ------------------------------------------------------------------
    # Helper: row widget with a QLineEdit + browse button
    # ------------------------------------------------------------------

    def _browse_row(self, field: QLineEdit, callback) -> QWidget:
        """Return a QWidget containing [field  …] for use in a QFormLayout."""
        w = QWidget()
        h = QHBoxLayout(w)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(4)
        h.addWidget(field)
        btn = QPushButton("…")
        btn.setFixedSize(28, 26)
        btn.setStyleSheet(
            "QPushButton { padding: 0; font-size: 14px; background:#1e293b; border:1px solid rgba(255,255,255,0.12); border-radius:4px; }"
            "QPushButton:hover { background:#334155; }"
        )
        btn.clicked.connect(callback)
        h.addWidget(btn)
        return w

    def _build_quick_config(self) -> QWidget:
        from PySide6.QtWidgets import QScrollArea

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(scroll.Shape.NoFrame)

        inner = QWidget()
        layout = QVBoxLayout(inner)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        # ---- Paths ----
        paths_box = QGroupBox("Paths")
        pf = QFormLayout(paths_box)
        pf.setVerticalSpacing(6)
        pf.setHorizontalSpacing(10)
        pf.setContentsMargins(8, 14, 8, 8)

        self._qc_root       = QLineEdit()
        self._qc_plugins_dir = QLineEdit()
        self._qc_video       = QLineEdit()
        self._qc_model       = QLineEdit()
        self._qc_plugins     = QLineEdit()

        self._qc_root.setPlaceholderText(r"D:\Projects\SVG_HOPE  (optional)")
        self._qc_plugins_dir.setPlaceholderText(r"D:\my_plugins\  (optional, standalone)")
        self._qc_video.setPlaceholderText(r"D:\videos\test.mp4")
        self._qc_model.setPlaceholderText(r"models\yolov8n.onnx")
        self._qc_plugins.setPlaceholderText("speeding, stop_line, …")

        # Restore last-used paths from QSettings
        _s = QSettings("HOPEPluginTester", "ScenarioPanel")
        self._qc_root.setText(_s.value("qc_root", ""))
        self._qc_plugins_dir.setText(_s.value("qc_plugins_dir", ""))
        self._qc_video.setText(_s.value("qc_video", ""))
        self._qc_model.setText(_s.value("qc_model", ""))

        root_lbl = QLabel("SVG_HOPE root:")
        root_lbl.setToolTip(
            "Path to your SVG_HOPE installation.\n"
            "Required for SVG_HOPE violation plugins.\n"
            "Leave blank to run detection+tracking only, "
            "or set a standalone Plugins dir instead."
        )

        pf.addRow(root_lbl,
            self._browse_row(self._qc_root, lambda: self._pick_dir(self._qc_root)))

        pdir_lbl = QLabel("Plugins dir:")
        pdir_lbl.setToolTip(
            "Standalone plugins folder — no SVG_HOPE required.\n"
            "Each .py file must expose  process_context(ctx) -> list[dict]."
        )
        pf.addRow(pdir_lbl,
            self._browse_row(self._qc_plugins_dir, lambda: self._pick_dir(self._qc_plugins_dir)))

        pf.addRow("Video file:",
            self._browse_row(self._qc_video, lambda: self._pick_video(self._qc_video)))
        pf.addRow("ONNX model:",
            self._browse_row(self._qc_model, lambda: self._pick_onnx(self._qc_model)))
        pf.addRow("Plugins:",
            self._browse_row(self._qc_plugins, self._pick_plugins))

        # ---- Camera ----
        cam_box = QGroupBox("Camera")
        cf = QFormLayout(cam_box)
        cf.setVerticalSpacing(6)
        cf.setHorizontalSpacing(10)
        cf.setContentsMargins(8, 14, 8, 8)

        self._qc_name  = QLineEdit("cam1")
        self._qc_limit = QSpinBox()
        self._qc_limit.setRange(1, 200)
        self._qc_limit.setValue(30)
        self._qc_ppm   = QDoubleSpinBox()
        self._qc_ppm.setRange(0.1, 500.0)
        self._qc_ppm.setDecimals(2)
        self._qc_ppm.setValue(8.5)
        self._qc_frame_skip = QSpinBox()
        self._qc_frame_skip.setRange(1, 10)
        self._qc_frame_skip.setValue(2)
        self._qc_frame_skip.setToolTip(
            "Run detection every N frames.\n"
            "1 = every frame (slowest/most accurate)\n"
            "2 = every other frame (recommended)\n"
            "3+ = faster but may miss short events"
        )

        self._qc_device = QComboBox()
        self._qc_device.addItems(["auto", "cpu", "dml", "cuda"])
        self._qc_device.setToolTip(
            "auto — picks CUDA > DirectML > CPU automatically\n"
            "cpu  — force CPU (always available)\n"
            "dml  — AMD Radeon / Intel / NVIDIA via DirectML (DX12)\n"
            "       install: pip install onnxruntime-directml\n"
            "cuda — NVIDIA CUDA (install: pip install onnxruntime-gpu)"
        )

        cf.addRow("Camera name:",     self._qc_name)
        cf.addRow("Speed limit mph:", self._qc_limit)
        cf.addRow("Pixels / metre:",  self._qc_ppm)
        cf.addRow("Frame skip:",      self._qc_frame_skip)
        cf.addRow("Device:",          self._qc_device)

        # ---- Apply button ----
        apply_btn = QPushButton("Apply to Script  ▸")
        apply_btn.setObjectName("primary")
        apply_btn.clicked.connect(self._qc_to_script)

        layout.addWidget(paths_box)
        layout.addWidget(cam_box)
        layout.addWidget(apply_btn)
        layout.addStretch()

        scroll.setWidget(inner)
        return scroll

    # Browse helpers -------------------------------------------------------

    def _pick_dir(self, field: QLineEdit) -> None:
        start = field.text() or ""
        p = QFileDialog.getExistingDirectory(self, "Select Directory", start)
        if p:
            field.setText(p)

    def _pick_video(self, field: QLineEdit) -> None:
        start = os.path.dirname(field.text()) if field.text() else ""
        p, _ = QFileDialog.getOpenFileName(
            self, "Select Video File", start,
            "Video files (*.mp4 *.avi *.mkv *.mov *.wmv *.ts *.m4v);;All files (*)"
        )
        if p:
            field.setText(p)

    def _pick_onnx(self, field: QLineEdit) -> None:
        start = os.path.dirname(field.text()) if field.text() else ""
        p, _ = QFileDialog.getOpenFileName(
            self, "Select ONNX Model", start,
            "ONNX models (*.onnx);;All files (*)"
        )
        if p:
            field.setText(p)

    def _pick_plugins(self) -> None:
        """Open a checkbox dialog to select violation plugins from the SVG_HOPE root."""
        root = self._qc_root.text().strip()
        violations_dir = os.path.join(root, "plugins", "violations") if root else ""

        # Collect plugin ids: scan violations dir for *.py files, else use built-in list
        plugin_ids: list = []
        if violations_dir and os.path.isdir(violations_dir):
            for fname in sorted(os.listdir(violations_dir)):
                if fname.endswith(".py") and not fname.startswith("_"):
                    plugin_ids.append(fname[:-3])
        if not plugin_ids:
            plugin_ids = [
                "speeding", "stop_line", "illegal_lane_change",
                "illegal_overtaking", "wrong_way", "no_parking",
                "gore_incursion", "illegal_turn", "reckless_driving",
                "roundabout_wrong_way",
            ]

        current = {p.strip() for p in self._qc_plugins.text().split(",") if p.strip()}

        dlg = QDialog(self)
        dlg.setWindowTitle("Select Plugins")
        dlg.setMinimumWidth(280)
        dlg_layout = QVBoxLayout(dlg)
        dlg_layout.setSpacing(6)

        if violations_dir and os.path.isdir(violations_dir):
            lbl = QLabel(f"From: {violations_dir}")
            lbl.setStyleSheet("color:#94a3b8; font-size:10px;")
            lbl.setWordWrap(True)
            dlg_layout.addWidget(lbl)
        else:
            lbl = QLabel("Set SVG_HOPE root first to auto-discover plugins.\nShowing built-in list:")
            lbl.setStyleSheet("color:#f59e0b; font-size:10px;")
            lbl.setWordWrap(True)
            dlg_layout.addWidget(lbl)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        inner = QWidget()
        inner_layout = QVBoxLayout(inner)
        inner_layout.setSpacing(4)
        inner_layout.setContentsMargins(4, 4, 4, 4)

        checkboxes: list = []
        for pid in plugin_ids:
            cb = QCheckBox(pid)
            cb.setChecked(pid in current)
            inner_layout.addWidget(cb)
            checkboxes.append(cb)

        inner_layout.addStretch()
        scroll.setWidget(inner)
        dlg_layout.addWidget(scroll)

        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        btns.accepted.connect(dlg.accept)
        btns.rejected.connect(dlg.reject)
        dlg_layout.addWidget(btns)

        if dlg.exec() == QDialog.DialogCode.Accepted:
            selected = [cb.text() for cb in checkboxes if cb.isChecked()]
            self._qc_plugins.setText(", ".join(selected))

    def _qc_to_script(self) -> None:
        root        = self._qc_root.text()
        plugins_dir = self._qc_plugins_dir.text()
        video   = self._qc_video.text()
        model   = self._qc_model.text()
        plugins = [p.strip() for p in self._qc_plugins.text().split(",") if p.strip()]
        name       = self._qc_name.text() or "cam1"
        limit      = self._qc_limit.value()
        ppm        = self._qc_ppm.value()
        frame_skip = self._qc_frame_skip.value()
        device     = self._qc_device.currentText()

        # Persist paths so they survive restarts
        _s = QSettings("HOPEPluginTester", "ScenarioPanel")
        _s.setValue("qc_root",        root)
        _s.setValue("qc_plugins_dir", plugins_dir)
        _s.setValue("qc_video",       video)
        _s.setValue("qc_model",       model)

        plugin_list = repr(plugins)
        plugin_cfgs = "{" + ", ".join(f'"{p}": {{}}' for p in plugins) + "}"

        # Build the optional path lines (omit blank ones so the script stays clean)
        path_lines = [f's.video_path    = r"{video}"', f's.model_path    = r"{model}"']
        if root:
            path_lines.insert(0, f's.svg_hope_root = r"{root}"')
        if plugins_dir:
            path_lines.append(f's.plugins_dir   = r"{plugins_dir}"')
        path_block = "\n".join(path_lines)

        script = f'''\
from scenarios.base import Scenario, Camera, Lane, ViolationAssertion

s = Scenario("quick_config")
{path_block}
s.device = "{device}"  # auto | cpu | dml (AMD Radeon DirectML) | cuda (NVIDIA)

s.plugins = {plugin_list}
s.plugin_config = {plugin_cfgs}

s.camera = Camera(
    name="{name}",
    speed_limit_mph={limit},
    pixels_per_meter={ppm},
)
s.frame_skip = {frame_skip}  # detect every N frames (2 = ~2x faster)

# Add lanes below \u2014 boundaries are polygon corner points (x, y) in pixels
s.lanes = [
    Lane(lane_id=0, boundaries=[(0, 0), (1280, 0), (1280, 720), (0, 720)],
         speed_limit_mph={limit}),
]

s.assertions = []
'''
        self._editor.setPlainText(script)
        self._tabs.setCurrentIndex(0)
