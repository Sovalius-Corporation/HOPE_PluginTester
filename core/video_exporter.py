"""VideoExporter -- burns detection overlays onto video frames and writes an MP4.

Usage (from session.py)::

    exporter = VideoExporter(output_path, fps, width, height)
    exporter.write(frame, tracks, violations)   # per frame
    path = exporter.finish()                    # releases writer, returns path
"""
from __future__ import annotations

import logging

import cv2
import numpy as np

logger = logging.getLogger(__name__)


class VideoExporter:
    """Writes an annotated video to disk using OpenCV VideoWriter."""

    def __init__(self, output_path: str, fps: float, width: int, height: int) -> None:
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        self._writer = cv2.VideoWriter(output_path, fourcc, max(fps, 1.0), (width, height))
        self._path = output_path
        self._active = self._writer.isOpened()
        self._frames = 0
        if not self._active:
            logger.warning("VideoExporter: cannot open output path %s", output_path)

    def write(self, frame: np.ndarray, tracks: list, violations: list) -> None:
        if not self._active:
            return
        out = self._annotate(frame, tracks, violations)
        self._writer.write(out)
        self._frames += 1

    def finish(self) -> str:
        if self._active:
            self._writer.release()
            self._active = False
            logger.info("VideoExporter: saved %d frames to %s", self._frames, self._path)
        return self._path

    def is_active(self) -> bool:
        return self._active

    # ------------------------------------------------------------------

    def _annotate(self, frame: np.ndarray, tracks: list, violations: list) -> np.ndarray:
        out = frame.copy()
        vids = {v.get("track_id") for v in violations}
        for t in tracks:
            x1, y1, x2, y2 = (int(c) for c in t.bbox)
            is_viol = t.track_id in vids
            # BGR: red for violation, green otherwise
            col = (50, 50, 230) if is_viol else (50, 200, 50)
            cv2.rectangle(out, (x1, y1), (x2, y2), col, 2)

            label = f"#{t.track_id}"
            spd = getattr(t, "speed_mph", 0)
            if spd:
                label += f" {spd:.0f}mph"
            plate = getattr(t, "license_plate", "")
            if plate:
                label += f" {plate}"

            # Text background
            (tw, th), bl = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.45, 1)
            ty = max(y1 - 4, th + 4)
            cv2.rectangle(out, (x1, ty - th - bl), (x1 + tw + 4, ty + 2), (0, 0, 0), -1)
            cv2.putText(out, label, (x1 + 2, ty), cv2.FONT_HERSHEY_SIMPLEX, 0.45, col, 1, cv2.LINE_AA)

            if is_viol:
                # Violation badge
                vtype = next((v.get("type","!") for v in violations if v.get("track_id") == t.track_id), "!")
                badge = f"! {vtype}"
                (bw, bh), bbl = cv2.getTextSize(badge, cv2.FONT_HERSHEY_SIMPLEX, 0.4, 1)
                bx, by = x1, y1 - th - 10
                if by > bh + 4:
                    cv2.rectangle(out, (bx, by - bh - bbl), (bx + bw + 6, by + 2), (0, 0, 180), -1)
                    cv2.putText(out, badge, (bx + 3, by), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 255, 255), 1, cv2.LINE_AA)
        return out
