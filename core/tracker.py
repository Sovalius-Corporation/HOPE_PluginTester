"""Simple IoU-based vehicle tracker.

Greedy assignment: highest-IoU pair claimed first, unmatched detections
become new tracks, tracks not seen for ``max_unseen`` frames are dropped.
"""
from __future__ import annotations

import logging
from collections import deque
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)

_HISTORY_LEN = 30   # max position history kept per track
_MAX_UNSEEN = 8     # frames before a track is dropped
_IOU_THRESHOLD = 0.30


@dataclass
class Track:
    track_id: int
    bbox: Tuple[int, int, int, int]          # x1, y1, x2, y2
    vehicle_type: str
    confidence: float
    frames_tracked: int = 1
    frames_since_seen: int = 0
    position_history: deque = field(default_factory=lambda: deque(maxlen=_HISTORY_LEN))
    speed_mph: float = 0.0
    license_plate: Optional[str] = None
    plate_confidence: Optional[float] = None


def _iou(a: Tuple, b: Tuple) -> float:
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    ix1 = max(ax1, bx1); iy1 = max(ay1, by1)
    ix2 = min(ax2, bx2); iy2 = min(ay2, by2)
    if ix2 <= ix1 or iy2 <= iy1:
        return 0.0
    inter = (ix2 - ix1) * (iy2 - iy1)
    aa = (ax2 - ax1) * (ay2 - ay1)
    ab = (bx2 - bx1) * (by2 - by1)
    union = aa + ab - inter
    return inter / union if union > 0 else 0.0


def _center(bbox: Tuple) -> Tuple[float, float]:
    x1, y1, x2, y2 = bbox
    return ((x1 + x2) / 2.0, (y1 + y2) / 2.0)


class IoUTracker:
    """Greedy IoU tracker with stale-track pruning."""

    def __init__(
        self,
        iou_threshold: float = _IOU_THRESHOLD,
        max_unseen: int = _MAX_UNSEEN,
    ) -> None:
        self._tracks: Dict[int, Track] = {}
        self._next_id = 1
        self.iou_threshold = iou_threshold
        self.max_unseen = max_unseen

    # ------------------------------------------------------------------

    def update(self, detections: List[Dict]) -> List[Track]:
        """Match detections to existing tracks; return all active tracks."""
        track_ids = list(self._tracks.keys())
        tracks = [self._tracks[tid] for tid in track_ids]

        matched_tids: set = set()
        matched_dets: set = set()

        if tracks and detections:
            iou_mat = np.zeros((len(tracks), len(detections)))
            for ti, t in enumerate(tracks):
                for di, d in enumerate(detections):
                    iou_mat[ti, di] = _iou(t.bbox, d["bbox"])

            # Greedy: claim best pair until all remaining pairs < threshold
            while iou_mat.max() >= self.iou_threshold:
                ti, di = np.unravel_index(iou_mat.argmax(), iou_mat.shape)
                tid = track_ids[ti]
                det = detections[di]
                t = self._tracks[tid]

                t.bbox = det["bbox"]
                t.vehicle_type = det["vehicle_type"]
                t.confidence = det["confidence"]
                t.frames_tracked += 1
                t.frames_since_seen = 0
                t.position_history.append(_center(det["bbox"]))

                matched_tids.add(tid)
                matched_dets.add(di)
                iou_mat[ti, :] = -1.0
                iou_mat[:, di] = -1.0

        # Age unmatched tracks
        for tid in track_ids:
            if tid not in matched_tids:
                self._tracks[tid].frames_since_seen += 1

        # Drop stale
        stale = [tid for tid, t in self._tracks.items() if t.frames_since_seen >= self.max_unseen]
        for tid in stale:
            del self._tracks[tid]

        # New tracks for unmatched detections
        for di, det in enumerate(detections):
            if di not in matched_dets:
                tid = self._next_id
                self._next_id += 1
                t = Track(
                    track_id=tid,
                    bbox=det["bbox"],
                    vehicle_type=det["vehicle_type"],
                    confidence=det["confidence"],
                )
                t.position_history.append(_center(det["bbox"]))
                self._tracks[tid] = t

        return list(self._tracks.values())

    def reset(self) -> None:
        self._tracks.clear()
        self._next_id = 1
