"""VideoPanel — displays the live video frame with detection overlays.

Overlays painted via QPainter using the same translate+scale approach as
SVG_HOPE's gl_video_widget so all drawing is done in frame-pixel coordinates.

Overlays:
  • Lane polygon fills (translucent green) + solid/dashed left+right edges
  • Lane name label centred in lane
  • Direction arrow pointing along direction_angle
  • Stop lines (thick white, 8 px)
  • Vehicle bounding boxes (green normal / red violation)
  • Track label:  ID · type · speed
  • Violation badge above bbox
"""
from __future__ import annotations

import math
from typing import List, Optional

import numpy as np
from PySide6.QtCore import Qt, QRect, QPointF, QRectF
from PySide6.QtGui import (
    QColor, QFont, QImage, QPainter, QPainterPath, QPen,
    QPixmap, QBrush, QPolygonF,
)
from PySide6.QtWidgets import QSizePolicy, QWidget


# ── colour palette ────────────────────────────────────────────────────────────
_COL_NORMAL    = QColor(34, 197, 94,  220)   # green   bbox
_COL_VIOLATION = QColor(239, 68,  68,  230)   # red     bbox violation
_COL_LANE_FILL = QColor(0,   200, 0,   64)    # green translucent fill  (SVG_HOPE default)
_COL_LANE_LINE = QColor(255, 255, 255, 210)   # white  lane edges
_COL_STOP_LINE = QColor(255, 255, 255, 230)   # white  stop lines
_COL_ARROW     = QColor(255, 255, 255, 220)
_COL_BADGE_BG  = QColor(239, 68,  68,  210)
_COL_BADGE_TXT = QColor(255, 255, 255)
_COL_TEXT_BG   = QColor(0,   0,   0,   170)


def _numpy_to_qpixmap(frame: np.ndarray) -> QPixmap:
    h, w, ch = frame.shape
    rgb = frame[:, :, ::-1].copy()           # BGR → RGB, C-contiguous
    img = QImage(rgb.data, w, h, w * ch, QImage.Format.Format_RGB888)
    return QPixmap.fromImage(img)


def _poly_center(pts) -> QPointF:
    cx = sum(p[0] for p in pts) / len(pts)
    cy = sum(p[1] for p in pts) / len(pts)
    return QPointF(cx, cy)


class VideoPanel(QWidget):
    """Displays video frames with detection + violation overlays."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setMinimumSize(480, 320)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setStyleSheet("background-color: #07090e;")

        self._pixmap: Optional[QPixmap] = None
        self._tracks: list = []
        self._violations: list = []
        self._violation_ids: set = set()
        self._scenario = None

        # Overlay visibility flags
        self._show_lanes:  bool = True
        self._show_tracks: bool = True
        self._show_labels: bool = True

        # Frozen snapshot (set by clicking a violation row)
        self._snapshot_pixmap: Optional[QPixmap] = None

        self._font_label = QFont("Consolas", 8, QFont.Weight.Bold)
        self._font_badge = QFont("Consolas", 7, QFont.Weight.Bold)
        self._font_idle  = QFont("Segoe UI", 11)
        self._font_lane  = QFont("Segoe UI", 10, QFont.Weight.Bold)

    # ------------------------------------------------------------------
    # Public slots
    # ------------------------------------------------------------------

    def update_frame(self, frame: np.ndarray, tracks: list, violations: list) -> None:
        self._pixmap = _numpy_to_qpixmap(frame)
        self._tracks = tracks
        self._violations = violations
        self._violation_ids = {v.get("track_id") for v in violations}
        self.update()

    def set_scenario(self, scenario) -> None:
        self._scenario = scenario

    def clear(self) -> None:
        self._pixmap = None
        self._snapshot_pixmap = None
        self._tracks = []
        self._violations = []
        self._violation_ids = set()
        self.update()

    # ------------------------------------------------------------------
    # Overlay toggle API (called by toolbar buttons)
    # ------------------------------------------------------------------

    def toggle_lanes(self) -> bool:
        """Toggle lane overlay; returns new state."""
        self._show_lanes = not self._show_lanes
        self.update()
        return self._show_lanes

    def toggle_tracks(self) -> bool:
        """Toggle bounding-box overlay; returns new state."""
        self._show_tracks = not self._show_tracks
        self.update()
        return self._show_tracks

    def toggle_labels(self) -> bool:
        """Toggle track labels; returns new state."""
        self._show_labels = not self._show_labels
        self.update()
        return self._show_labels

    # ------------------------------------------------------------------
    # Snapshot API (show a frozen violation frame)
    # ------------------------------------------------------------------

    def show_snapshot(self, jpeg_bytes: bytes) -> None:
        """Freeze the panel on a stored violation frame."""
        from PySide6.QtGui import QImage
        img = QImage.fromData(jpeg_bytes)
        if not img.isNull():
            self._snapshot_pixmap = QPixmap.fromImage(img)
            self.update()

    def clear_snapshot(self) -> None:
        """Return to the live video stream."""
        self._snapshot_pixmap = None
        self.update()

    def save_current_frame(self) -> None:
        """Save whatever is currently displayed to a user-chosen file."""
        from PySide6.QtWidgets import QFileDialog
        path, _ = QFileDialog.getSaveFileName(
            self, "Save Frame", "frame.png",
            "PNG (*.png);;JPEG (*.jpg *.jpeg);;All files (*)",
        )
        if not path:
            return
        pix = self._snapshot_pixmap if self._snapshot_pixmap is not None else self._pixmap
        if pix is not None:
            pix.save(path)

    # ------------------------------------------------------------------
    # Context menu
    # ------------------------------------------------------------------

    def contextMenuEvent(self, event) -> None:
        from PySide6.QtWidgets import QMenu
        menu = QMenu(self)
        act_save  = menu.addAction("Save current frame as PNG…")
        act_clear = menu.addAction("Clear snapshot (return to live)")
        act_clear.setEnabled(self._snapshot_pixmap is not None)
        act = menu.exec(event.globalPos())
        if act == act_save:
            self.save_current_frame()
        elif act == act_clear:
            self.clear_snapshot()

    # ------------------------------------------------------------------
    # Paint
    # ------------------------------------------------------------------

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Prefer snapshot over live frame when one is set
        display_pixmap = (
            self._snapshot_pixmap
            if self._snapshot_pixmap is not None
            else self._pixmap
        )

        if display_pixmap is None:
            self._draw_idle(painter)
            painter.end()
            return

        # ── draw video frame centred, aspect-preserved ──────────────
        scaled = display_pixmap.scaled(
            self.size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        ox = (self.width()  - scaled.width())  // 2
        oy = (self.height() - scaled.height()) // 2
        painter.drawPixmap(ox, oy, scaled)

        # "SNAPSHOT" banner when showing a frozen frame
        if self._snapshot_pixmap is not None:
            banner_font = QFont("Consolas", 9, QFont.Weight.Bold)
            painter.setFont(banner_font)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(239, 68, 68, 200))
            fm = painter.fontMetrics()
            text = "\u2022 SNAPSHOT  (right-click to clear)"
            tw = fm.horizontalAdvance(text)
            th = fm.height()
            painter.drawRect(QRect(ox + 4, oy + 4, tw + 12, th + 6))
            painter.setPen(QColor(255, 255, 255))
            painter.drawText(QRect(ox + 4, oy + 4, tw + 12, th + 6),
                             Qt.AlignmentFlag.AlignCenter, text)

        if display_pixmap.width() <= 0 or display_pixmap.height() <= 0:
            painter.end()
            return

        sx = scaled.width()  / display_pixmap.width()
        sy = scaled.height() / display_pixmap.height()
        avg_s = (sx + sy) * 0.5

        # ── switch to frame-pixel coordinate space ───────────────────
        painter.save()
        painter.translate(ox, oy)
        painter.scale(sx, sy)

        if self._scenario and self._show_lanes:
            self._draw_lanes(painter, avg_s)

        if self._show_tracks:
            self._draw_tracks(painter, avg_s)

        painter.restore()
        painter.end()

    # ------------------------------------------------------------------
    # Lane drawing (SVG_HOPE style)
    # ------------------------------------------------------------------

    def _draw_lanes(self, painter: QPainter, avg_s: float) -> None:
        lanes = getattr(self._scenario, "lanes", [])
        stop_lines = getattr(self._scenario, "stop_lines", [])

        edge_w = max(6.0 / avg_s, 1.5)   # visually ~6 px at any zoom

        for lane in lanes:
            pts = lane.boundaries
            if len(pts) < 3:
                continue

            qpts = [QPointF(p[0], p[1]) for p in pts]
            poly = QPolygonF(qpts)

            # ── fill ──────────────────────────────────────────────
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(_COL_LANE_FILL))
            painter.drawPolygon(poly)

            # ── left / right edges ────────────────────────────────
            # For a 4-point clockwise polygon [TL, TR, BR, BL]:
            #   left edge  = pts[0] → pts[-1]
            #   right edge = pts[1] → pts[2]
            n = len(pts)
            if n == 4:
                edge_pairs = [
                    (pts[0], pts[3], getattr(lane, "left_line_type",  "solid")),
                    (pts[1], pts[2], getattr(lane, "right_line_type", "solid")),
                ]
            else:
                half = n // 2
                edge_pairs = [
                    (pts[0],        pts[n - 1], getattr(lane, "left_line_type",  "solid")),
                    (pts[half - 1], pts[half],  getattr(lane, "right_line_type", "solid")),
                ]

            painter.setBrush(Qt.BrushStyle.NoBrush)
            for p1, p2, ltype in edge_pairs:
                pen = QPen(_COL_LANE_LINE, edge_w, Qt.PenStyle.SolidLine,
                           Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
                if ltype == "dashed":
                    pen.setStyle(Qt.PenStyle.DashLine)
                painter.setPen(pen)
                painter.drawLine(QPointF(p1[0], p1[1]), QPointF(p2[0], p2[1]))

            # ── direction arrow ───────────────────────────────────
            angle_deg = getattr(lane, "direction_angle", None)
            if angle_deg is not None:
                ctr = _poly_center(pts)
                # estimate lane half-width for arrow size
                dx = pts[1][0] - pts[0][0]
                dy = pts[1][1] - pts[0][1]
                hw = math.hypot(dx, dy) * 0.12   # 12% of top-edge width
                hw = max(hw, 10.0)
                rad = math.radians(angle_deg)
                perp = rad + math.pi / 2
                tip_x  = ctr.x() + math.cos(rad) * hw * 2
                tip_y  = ctr.y() - math.sin(rad) * hw * 2
                lw_x   = ctr.x() + math.cos(perp) * hw
                lw_y   = ctr.y() - math.sin(perp) * hw
                rw_x   = ctr.x() - math.cos(perp) * hw
                rw_y   = ctr.y() + math.sin(perp) * hw
                arrow = QPolygonF([
                    QPointF(tip_x, tip_y),
                    QPointF(lw_x,  lw_y),
                    QPointF(rw_x,  rw_y),
                ])
                painter.setPen(QPen(_COL_ARROW, max(2.0 / avg_s, 0.5)))
                painter.setBrush(QBrush(_COL_ARROW))
                painter.drawPolygon(arrow)

            # ── lane name label ───────────────────────────────────
            name = getattr(lane, "name", None)
            if name:
                ctr = _poly_center(pts)
                font = QFont("Segoe UI", max(int(10.0 / avg_s), 6), QFont.Weight.Bold)
                painter.setFont(font)
                fm = painter.fontMetrics()
                tw = fm.horizontalAdvance(name)
                th = fm.height()
                pad = 4
                bg = QRectF(ctr.x() - tw / 2 - pad,
                            ctr.y() - th - pad / 2,
                            tw + pad * 2, th + pad)
                painter.setBrush(QColor(0, 0, 0, 180))
                painter.setPen(Qt.PenStyle.NoPen)
                painter.drawRect(bg)
                painter.setPen(QPen(QColor(255, 255, 255)))
                painter.drawText(QPointF(ctr.x() - tw / 2, ctr.y() - pad / 2), name)

        # ── stop lines ────────────────────────────────────────────────
        stop_w = max(8.0 / avg_s, 2.0)
        pen = QPen(_COL_STOP_LINE, stop_w, Qt.PenStyle.SolidLine,
                   Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        for sl in stop_lines:
            for i in range(len(sl) - 1):
                painter.drawLine(QPointF(sl[i][0], sl[i][1]),
                                 QPointF(sl[i + 1][0], sl[i + 1][1]))

    # ------------------------------------------------------------------
    # Track / bbox drawing
    # ------------------------------------------------------------------

    def _draw_tracks(self, painter: QPainter, avg_s: float) -> None:
        box_w  = max(2.0 / avg_s, 0.8)
        font_pt = max(int(9.0 / avg_s), 5)
        font   = QFont("Consolas", font_pt, QFont.Weight.Bold)
        painter.setFont(font)
        fm = painter.fontMetrics()

        for track in self._tracks:
            x1, y1, x2, y2 = track.bbox
            in_viol = track.track_id in self._violation_ids
            col = _COL_VIOLATION if in_viol else _COL_NORMAL

            # bbox rectangle
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QPen(col, box_w))
            painter.drawRect(QRectF(x1, y1, x2 - x1, y2 - y1))

            # Compute label geometry (needed for badge even when labels hidden)
            label = f"ID:{track.track_id}  {track.vehicle_type}"
            if track.speed_mph > 0:
                label += f"  {track.speed_mph:.0f}mph"
            if track.license_plate:
                label += f"  [{track.license_plate}]"

            th = fm.height()
            lx = float(x1)
            ly = float(y1) - th - 2
            if ly < 0:
                ly = float(y2) + 2

            if self._show_labels:
                tw = fm.horizontalAdvance(label)
                painter.setBrush(QBrush(_COL_TEXT_BG))
                painter.setPen(Qt.PenStyle.NoPen)
                painter.drawRect(QRectF(lx - 1, ly, tw + 4, th))
                painter.setPen(QPen(col))
                painter.drawText(QPointF(lx + 1, ly + th - 2), label)

            # violation badge
            if in_viol and self._show_labels:
                vtypes = [v.get("type", "violation") for v in self._violations
                          if v.get("track_id") == track.track_id]
                if vtypes:
                    badge = vtypes[0].upper().replace("_", " ")
                    bw = fm.horizontalAdvance(badge) + 8
                    bh = th + 4
                    by = ly - bh - 2
                    painter.setBrush(QBrush(_COL_BADGE_BG))
                    painter.setPen(Qt.PenStyle.NoPen)
                    # drawRoundedRect needs QRectF
                    painter.drawRoundedRect(QRectF(lx, by, bw, bh), 4, 4)
                    painter.setPen(QPen(_COL_BADGE_TXT))
                    painter.drawText(QPointF(lx + 4, by + bh - 4), badge)

    # ------------------------------------------------------------------
    # Idle screen
    # ------------------------------------------------------------------

    def _draw_idle(self, painter: QPainter) -> None:
        painter.fillRect(self.rect(), QColor(7, 9, 14))
        painter.setFont(self._font_idle)
        painter.setPen(QColor(80, 90, 120))
        painter.drawText(
            self.rect(), Qt.AlignmentFlag.AlignCenter,
            "No video — configure a scenario and click Run ▶",
        )
