"""Per-track speed estimation from bbox centre displacement.

speed_mph = displacement_px_per_frame × fps / pixels_per_meter × 2.23694
A rolling average over the last N samples smooths per-frame jitter.
"""
from __future__ import annotations

import math
from collections import deque
from typing import Deque, Dict, Tuple


class SpeedEstimator:
    def __init__(
        self,
        pixels_per_meter: float = 10.0,
        fps: float = 30.0,
        smoothing_window: int = 10,
    ) -> None:
        self.pixels_per_meter = pixels_per_meter
        self.fps = fps
        self.smoothing_window = smoothing_window
        self._samples: Dict[int, Deque[float]] = {}

    # ------------------------------------------------------------------

    def update(self, track_id: int, position_history: "deque[Tuple[float,float]]") -> float:
        """Compute smoothed speed (mph) from the last two history positions."""
        if len(position_history) < 2 or self.pixels_per_meter <= 0:
            return self.get_speed(track_id)

        p1 = position_history[-2]
        p2 = position_history[-1]
        dist_px = math.hypot(p2[0] - p1[0], p2[1] - p1[1])

        speed_mps = (dist_px * self.fps) / self.pixels_per_meter
        speed_mph = speed_mps * 2.23694

        if track_id not in self._samples:
            self._samples[track_id] = deque(maxlen=self.smoothing_window)
        self._samples[track_id].append(speed_mph)

        q = self._samples[track_id]
        return sum(q) / len(q)

    def get_speed(self, track_id: int) -> float:
        q = self._samples.get(track_id)
        if not q:
            return 0.0
        return sum(q) / len(q)

    def remove_track(self, track_id: int) -> None:
        self._samples.pop(track_id, None)

    def reconfigure(self, pixels_per_meter: float, fps: float) -> None:
        self.pixels_per_meter = pixels_per_meter
        self.fps = fps
        self._samples.clear()
