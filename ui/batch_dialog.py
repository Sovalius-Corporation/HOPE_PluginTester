"""BatchDialog -- run a scenario against a folder of video files in sequence.

Runs detection + tracking (no plugins) for each video and reports per-file
metrics.  Plugin overhead is excluded so batch mode works without SVG_HOPE.
"""
from __future__ import annotations

import logging
import os
import time
from typing import List, Optional

from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import (
    QDialog,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QProgressBar,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

logger = logging.getLogger(__name__)

_EXTS = {".mp4", ".avi", ".mkv", ".mov", ".wmv", ".ts", ".m4v", ".flv"}


class _BatchThread(QThread):
    row_result = Signal(int, str, int, int, float)  # row, path, detections, tracks, duration
    log_line   = Signal(str)
    all_done   = Signal()

    def __init__(self, scenario, videos: List[str]) -> None:
        super().__init__()
        self._scn    = scenario
        self._videos = videos
        self._stop   = False

    def stop(self) -> None:
        self._stop = True

    def run(self) -> None:
        import cv2
        from core.detector import OnnxDetector
        from core.tracker  import IoUTracker
        from core.speed_estimator import SpeedEstimator

        scn = self._scn
        try:
            detector = OnnxDetector(
                scn.model_path,
                confidence_threshold=scn.confidence_threshold,
                device=getattr(scn, "device", "auto"),
            )
        except Exception as e:
            self.log_line.emit(f"[ERROR] Cannot load model: {e}")
            self.all_done.emit()
            return

        frame_skip = max(1, getattr(scn, "frame_skip", 2))

        for row, vpath in enumerate(self._videos):
            if self._stop:
                break
            self.log_line.emit(f"[{row+1}/{len(self._videos)}] {os.path.basename(vpath)}")
            t0 = time.monotonic()
            cap = cv2.VideoCapture(vpath)
            if not cap.isOpened():
                self.log_line.emit(f"  Cannot open: {vpath}")
                self.row_result.emit(row, vpath, -1, -1, 0.0)
                continue

            fps_src = cap.get(cv2.CAP_PROP_FPS) or 30.0
            tracker   = IoUTracker()
            speed_est = SpeedEstimator(scn.camera.pixels_per_meter, fps_src)

            total_dets = 0
            max_tracks = 0
            fi = 0
            last_dets: list = []

            while not self._stop:
                ret, frame = cap.read()
                if not ret:
                    break
                if fi % frame_skip == 0:
                    last_dets = detector.detect(frame)
                tracks = tracker.update(last_dets)
                for t in tracks:
                    t.speed_mph = speed_est.update(t.track_id, t.position_history)
                total_dets += len(last_dets)
                max_tracks = max(max_tracks, len(tracks))
                fi += 1

            cap.release()
            duration = time.monotonic() - t0
            avg_dets = total_dets // max(fi, 1)
            self.log_line.emit(f"  Done: {fi} frames, avg {avg_dets} det/frame, {duration:.1f}s")
            self.row_result.emit(row, vpath, avg_dets, max_tracks, duration)

        self.all_done.emit()


class BatchDialog(QDialog):
    """Run the current scenario's detector+tracker against a folder of videos."""

    def __init__(self, scenario, parent=None) -> None:
        super().__init__(parent)
        self._scn = scenario
        self._thread: Optional[_BatchThread] = None

        self.setWindowTitle("Batch Processing")
        self.setMinimumSize(680, 480)

        # Folder selector
        folder_box = QGroupBox("Video Folder")
        ff = QHBoxLayout(folder_box)
        self._folder = QLineEdit()
        self._folder.setPlaceholderText("Select a folder containing video files...")
        browse_btn = QPushButton("...")
        browse_btn.setFixedSize(28, 26)
        browse_btn.clicked.connect(self._pick)
        ff.addWidget(self._folder)
        ff.addWidget(browse_btn)

        # Results table
        self._table = QTableWidget(0, 5)
        self._table.setHorizontalHeaderLabels(["File", "Avg Det/frame", "Max Tracks", "Duration", "Status"])
        self._table.verticalHeader().setVisible(False)
        self._table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setAlternatingRowColors(True)

        # Progress
        self._progress = QProgressBar()
        self._log_lbl  = QLabel("")
        self._log_lbl.setStyleSheet("color:#94a3b8;font-size:10px;")
        self._log_lbl.setWordWrap(True)

        # Buttons
        self._start_btn = QPushButton("Start Batch")
        self._start_btn.setObjectName("primary")
        self._stop_btn  = QPushButton("Stop")
        self._stop_btn.setEnabled(False)
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        btn_row.addWidget(self._start_btn)
        btn_row.addWidget(self._stop_btn)

        layout = QVBoxLayout(self)
        layout.addWidget(folder_box)
        layout.addWidget(self._table, stretch=1)
        layout.addWidget(self._progress)
        layout.addWidget(self._log_lbl)
        layout.addLayout(btn_row)

        self._start_btn.clicked.connect(self._on_start)
        self._stop_btn.clicked.connect(self._on_stop)

    def _pick(self) -> None:
        p = QFileDialog.getExistingDirectory(self, "Select video folder")
        if p:
            self._folder.setText(p)

    def _on_start(self) -> None:
        folder = self._folder.text().strip()
        if not folder or not os.path.isdir(folder):
            self._log_lbl.setText("Select a valid folder first.")
            return
        videos = sorted([
            os.path.join(folder, f)
            for f in os.listdir(folder)
            if os.path.splitext(f)[1].lower() in _EXTS
        ])
        if not videos:
            self._log_lbl.setText("No video files found.")
            return

        self._table.setRowCount(0)
        for v in videos:
            row = self._table.rowCount()
            self._table.insertRow(row)
            self._table.setItem(row, 0, QTableWidgetItem(os.path.basename(v)))
            for c in range(1, 5):
                self._table.setItem(row, c, QTableWidgetItem("..."))

        self._progress.setMaximum(len(videos))
        self._progress.setValue(0)
        self._start_btn.setEnabled(False)
        self._stop_btn.setEnabled(True)
        self._log_lbl.setText("")

        self._thread = _BatchThread(self._scn, videos)
        self._thread.row_result.connect(self._on_result)
        self._thread.log_line.connect(lambda s: self._log_lbl.setText(s))
        self._thread.all_done.connect(self._on_done)
        self._thread.start()

    def _on_result(self, row: int, path: str, avg_dets: int, max_tracks: int, dur: float) -> None:
        self._progress.setValue(row + 1)
        if avg_dets < 0:
            vals = [os.path.basename(path), "—", "—", "—", "ERROR"]
        else:
            vals = [os.path.basename(path), str(avg_dets), str(max_tracks), f"{dur:.1f}s", "Done"]
        for c, val in enumerate(vals):
            item = QTableWidgetItem(val)
            if vals[-1] == "ERROR":
                from PySide6.QtGui import QColor
                item.setForeground(QColor(239, 68, 68))
            self._table.setItem(row, c, item)

    def _on_done(self) -> None:
        self._start_btn.setEnabled(True)
        self._stop_btn.setEnabled(False)
        self._log_lbl.setText("Batch complete.")

    def _on_stop(self) -> None:
        if self._thread:
            self._thread.stop()
        self._stop_btn.setEnabled(False)
