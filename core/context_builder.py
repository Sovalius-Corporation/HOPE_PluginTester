"""Builds SVG_HOPE ViolationContext objects from tracker state + scenario config.

Imports from the SVG_HOPE ``plugins`` package lazily — must be called after
``svg_hope_root`` has been inserted into ``sys.path`` by the session.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import TYPE_CHECKING, Any, List, Optional

import numpy as np

if TYPE_CHECKING:
    from core.tracker import Track
    from scenarios.base import Scenario

logger = logging.getLogger(__name__)


class ContextBuilder:
    """Converts ``Track`` objects into ``ViolationContext`` instances.

    Instantiate once per session after ``sys.path`` includes ``svg_hope_root``.
    """

    def __init__(self, scenario: "Scenario") -> None:
        from plugins.context import (
            CameraCalibration,
            LaneData,
            VehicleData,
            ViolationContext,
        )

        self._VehicleData = VehicleData
        self._CameraCalibration = CameraCalibration
        self._LaneData = LaneData
        self._ViolationContext = ViolationContext
        self._scn = scenario
        self._calibration = self._make_calibration()
        self._lanes = self._make_lanes()
        # Shared lane-history dict — mirrors what SVG_HOPE's PluginManager
        # does: one dict for all frames so get_vehicle_lane() hysteresis
        # (3-frame stability filter) works correctly across frames.
        # Keyed by (camera_name, track_id), same as the real PluginManager.
        self._lane_histories: dict = {}

    # ------------------------------------------------------------------

    def build(
        self,
        track: "Track",
        frame: np.ndarray,
        frame_index: int,
        fps: float,
        timestamp: Optional[datetime] = None,
    ) -> Any:
        """Return a ``ViolationContext`` for *track* at *frame_index*."""
        if timestamp is None:
            timestamp = datetime.now()

        vehicle = self._VehicleData(
            track_id=track.track_id,
            bbox=track.bbox,
            confidence=track.confidence,
            vehicle_type=track.vehicle_type,
            license_plate=track.license_plate,
            plate_confidence=track.plate_confidence,
            speed_mph=track.speed_mph,
            lane_index=None,
            position_history=list(track.position_history),
            timestamp=timestamp,
        )

        return self._ViolationContext(
            vehicle=vehicle,
            calibration=self._calibration,
            detected_lanes=self._lanes,
            stop_lines=self._scn.stop_lines,
            crossings=[],
            frame_index=frame_index,
            timestamp=timestamp,
            frame_shape=frame.shape,
            frame_buffer=frame,
            camera_name=self._scn.camera.name,
            inside_intersection=None,
            intersection_hub_type=None,
            inside_roundabout=None,
            inside_gore=None,
            allowed_next_lanes=None,
            mandatory_transition=None,
            road_network=None,
            tracking_confidence=track.confidence,
            frames_tracked=track.frames_tracked,
            fps=fps,
            schedule_rules=[],
            active_schedule_rules=[],
            active_schedule_overrides={},
            _lane_histories=self._lane_histories,  # shared across frames
        )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _make_calibration(self) -> Any:
        c = self._scn.camera
        return self._CameraCalibration(
            camera_name=c.name,
            location=c.location,
            coordinates=c.coordinates,
            pixels_per_meter=c.pixels_per_meter,
            fov_degrees=c.fov_degrees,
            speed_limit_mph=c.speed_limit_mph,
            is_built_up_area=c.is_built_up_area,
            country_code=c.country_code,
        )

    def _make_lanes(self) -> List[Any]:
        out = []
        for lc in self._scn.lanes:
            out.append(self._LaneData(
                lane_id=lc.lane_id,
                boundaries=lc.boundaries,
                expected_direction=lc.expected_direction,
                lane_type=lc.lane_type,
                speed_limit_mph=lc.speed_limit_mph,
                allows_overtaking=lc.allows_overtaking,
                direction_angle=lc.direction_angle,
                name=lc.name,
                left_line_type=lc.left_line_type,
                right_line_type=lc.right_line_type,
            ))
        return out
