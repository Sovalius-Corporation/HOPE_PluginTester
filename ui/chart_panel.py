"""ChartPanel -- live bar chart showing violation rate over time.

Buckets: 30-second windows.  Rolling window: 10 minutes (20 buckets).
Updated via add_violation() every time a violation fires, and redraws at 1 Hz.
"""
from __future__ import annotations

import time
from collections import deque
from typing import Deque, List

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QBrush, QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import QHBoxLayout, QLabel, QSizePolicy, QVBoxLayout, QWidget

_BUCKET_SEC  = 30
_MAX_BUCKETS = 20    # 20 x 30 s = 10 min


class ChartPanel(QWidget):
    """Bar chart of violations per 30-second window (last 10 min)."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)

        self._events: Deque[float] = deque()
        self._total = 0
        self._session_start = 0.0

        hdr = QLabel("VIOLATION RATE")
        hdr.setStyleSheet(
            "color:rgba(255,255,255,0.55);font-size:10px;font-weight:700;"
            "letter-spacing:2px;padding:6px 8px 2px 8px;"
        )
        self._info = QLabel("No session running.")
        self._info.setStyleSheet("color:#94a3b8;font-size:10px;padding:0 8px;")

        top = QHBoxLayout()
        top.setContentsMargins(0, 0, 0, 0)
        top.addWidget(hdr)
        top.addStretch()
        top.addWidget(self._info)

        self._canvas = _Canvas(self)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addLayout(top)
        layout.addWidget(self._canvas, stretch=1)

        self._timer = QTimer(self)
        self._timer.setInterval(1000)
        self._timer.timeout.connect(self._tick)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def start_session(self) -> None:
        self._events.clear()
        self._total = 0
        self._session_start = time.monotonic()
        self._timer.start()
        self._info.setText("Recording...")

    def stop_session(self) -> None:
        self._timer.stop()
        self._info.setText(f"Total violations: {self._total}")

    def add_violation(self, _violation: dict = None) -> None:
        self._events.append(time.monotonic())
        self._total += 1

    def clear(self) -> None:
        self._events.clear()
        self._total = 0
        self._timer.stop()
        self._canvas.set_data([])
        self._info.setText("No session running.")

    # ------------------------------------------------------------------

    def _tick(self) -> None:
        now = time.monotonic()
        cutoff = now - _MAX_BUCKETS * _BUCKET_SEC
        while self._events and self._events[0] < cutoff:
            self._events.popleft()

        buckets: List[int] = [0] * _MAX_BUCKETS
        for ts in self._events:
            idx = int((now - ts) / _BUCKET_SEC)
            if 0 <= idx < _MAX_BUCKETS:
                buckets[_MAX_BUCKETS - 1 - idx] += 1

        self._canvas.set_data(buckets)

        elapsed = now - self._session_start
        m, s = divmod(int(elapsed), 60)
        self._info.setText(f"{m:02d}:{s:02d}  |  total: {self._total}")


class _Canvas(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._buckets: List[int] = []
        self._font = QFont("Consolas", 8)

    def set_data(self, buckets: List[int]) -> None:
        self._buckets = buckets
        self.update()

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        W, H = self.width(), self.height()
        p.fillRect(0, 0, W, H, QColor(10, 15, 26))

        if not self._buckets:
            p.setPen(QColor(80, 90, 110))
            p.setFont(self._font)
            p.drawText(0, 0, W, H, Qt.AlignmentFlag.AlignCenter,
                       "Start a session to see the violations chart")
            p.end()
            return

        n  = len(self._buckets)
        mx = max(self._buckets) or 1
        PL, PR, PT, PB = 38, 10, 10, 22
        baw = W - PL - PR
        bah = H - PT - PB
        bw  = baw / n
        gap = max(bw * 0.15, 2.0)

        p.setPen(Qt.PenStyle.NoPen)
        for i, val in enumerate(self._buckets):
            bh = int(val / mx * bah)
            x  = int(PL + i * bw + gap / 2)
            y  = PT + bah - bh
            t  = val / mx
            r  = int(99  + t * 140)
            g  = int(102 - t * 34)
            b  = int(241 - t * 173)
            p.setBrush(QBrush(QColor(r, g, b)))
            p.drawRoundedRect(x, y, max(int(bw - gap), 2), bh, 2, 2)

        # Y-axis grid + labels
        p.setFont(self._font)
        for frac in (0.0, 0.5, 1.0):
            val = int(frac * mx)
            y   = int(PT + bah * (1.0 - frac))
            p.setPen(QColor(90, 100, 120))
            fm = p.fontMetrics()
            p.drawText(0, y - fm.height() // 2, PL - 4, fm.height(),
                       Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                       str(val))
            p.setPen(QPen(QColor(255, 255, 255, 18), 1, Qt.PenStyle.DashLine))
            p.drawLine(PL, y, W - PR, y)

        # X-axis labels every 5 buckets
        p.setPen(QColor(90, 100, 120))
        step = max(1, n // 5)
        for i in range(0, n, step):
            age = (_MAX_BUCKETS - i - 1) * _BUCKET_SEC
            lbl = f"-{age}s" if age < 60 else f"-{age // 60}m"
            x   = int(PL + (i + 0.5) * bw)
            p.drawText(x - 20, H - PB + 3, 40, PB - 3,
                       Qt.AlignmentFlag.AlignCenter, lbl)
        p.end()
