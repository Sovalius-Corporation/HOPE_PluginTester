"""Scenario DSL for HOPE Plugin Tester.

Usage (Python script, paste into the Script tab or run standalone)::

    from scenarios.base import Scenario, Camera, Lane, ViolationAssertion

    s = Scenario("speeding_basic")
    s.svg_hope_root = r"D:\\Projects\\SVG_HOPE"
    s.video_path    = r"D:\\videos\\highway.mp4"
    s.model_path    = r"D:\\Projects\\SVG_HOPE\\models\\yolov8n.onnx"

    s.plugins = ["speeding"]
    s.plugin_config = {"speeding": {"tolerance_mph": 0, "min_duration_sec": 1.0}}

    s.camera = Camera(name="cam1", speed_limit_mph=30, pixels_per_meter=8.5)
    s.lanes  = [Lane(lane_id=0,
                     boundaries=[(0,0),(1280,0),(1280,720),(0,720)],
                     speed_limit_mph=30)]

    s.assertions = [ViolationAssertion("speeding", min_count=1)]

    # Run headlessly (no UI)
    # result = s.run()
    # print(result.summary())
"""
from __future__ import annotations

import logging
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Camera and lane configuration
# ---------------------------------------------------------------------------

@dataclass
class Camera:
    """Camera calibration parameters used to populate CameraCalibration."""
    name: str = "cam1"
    speed_limit_mph: int = 30
    pixels_per_meter: float = 10.0
    location: str = ""
    coordinates: Optional[Tuple[float, float]] = None
    fov_degrees: Optional[float] = None
    is_built_up_area: bool = True
    country_code: str = "US"


@dataclass
class Lane:
    """Lane configuration used to populate LaneData."""
    lane_id: int = 0
    boundaries: List[Tuple[int, int]] = field(default_factory=list)
    direction_angle: float = 0.0
    expected_direction: str = "north"
    lane_type: str = "regular"
    speed_limit_mph: int = 30
    allows_overtaking: bool = True
    name: str = ""
    left_line_type: str = "solid"
    right_line_type: str = "solid"


# ---------------------------------------------------------------------------
# Assertion types
# ---------------------------------------------------------------------------

@dataclass
class ViolationAssertion:
    """Declare an expected outcome for a test scenario."""
    violation_type: str
    min_count: int = 1
    max_count: Optional[int] = None
    track_id: Optional[int] = None  # None = any track


@dataclass
class AssertionResult:
    assertion: ViolationAssertion
    actual_count: int
    passed: bool
    message: str


@dataclass
class ScenarioResult:
    scenario_name: str
    total_violations: int
    violations: List[Dict[str, Any]]
    assertion_results: List[AssertionResult]
    all_passed: bool

    def summary(self) -> str:
        lines = [
            f"Scenario : {self.scenario_name}",
            f"Violations: {self.total_violations}",
        ]
        for ar in self.assertion_results:
            tag = "PASS" if ar.passed else "FAIL"
            lines.append(f"  [{tag}] {ar.message}")
        overall = "ALL PASSED" if self.all_passed else "FAILED"
        lines.append(f"Result: {overall}")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Scenario
# ---------------------------------------------------------------------------

class Scenario:
    """Full test scenario.  Configure, then call ``run()`` or hand to the UI."""

    def __init__(self, name: str = "unnamed") -> None:
        self.name: str = name

        # Paths
        self.svg_hope_root: str = ""   # Optional — only needed for SVG_HOPE violation plugins
        self.plugins_dir: str = ""     # Optional — standalone plugins folder (no SVG_HOPE needed)
        self.video_path: str = ""
        self.model_path: str = ""

        # Detection
        self.detector_type: str = "auto"      # "yolov8" | "rtdetr" | "auto"
        self.confidence_threshold: float = 0.3
        self.device: str = "auto"             # "auto" | "cpu" | "dml" | "cuda"

        # Plugins
        self.plugins: List[str] = []
        self.plugin_config: Dict[str, Dict] = {}

        # Scene geometry
        self.camera: Camera = Camera()
        self.lanes: List[Lane] = []
        self.stop_lines: List[List[Tuple[int, int]]] = []

        # LPR
        self.lpr_enabled: bool = False
        self.lpr_model_path: str = ""

        # Assertions
        self.assertions: List[ViolationAssertion] = []

        # Limits
        self.max_frames: Optional[int] = None   # None = full video
        # Run detection every N frames; tracks update every frame.
        # 1 = every frame (default), 2 = every other frame (2x faster), etc.
        self.frame_skip: int = 1

    # ------------------------------------------------------------------
    # Headless run (no UI)
    # ------------------------------------------------------------------

    def run(self) -> ScenarioResult:
        """Execute headlessly and return a :class:`ScenarioResult`."""
        root = str(Path(self.svg_hope_root).resolve())
        if root not in sys.path:
            sys.path.insert(0, root)

        import cv2
        from core.context_builder import ContextBuilder
        from core.detector import OnnxDetector
        from core.speed_estimator import SpeedEstimator
        from core.tracker import IoUTracker
        from plugins.plugin_manager import PluginManager

        detector = OnnxDetector(self.model_path, self.confidence_threshold)
        tracker = IoUTracker()

        cap = cv2.VideoCapture(self.video_path)
        if not cap.isOpened():
            raise RuntimeError(f"Cannot open video: {self.video_path}")

        fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        speed_est = SpeedEstimator(
            pixels_per_meter=self.camera.pixels_per_meter,
            fps=fps,
        )
        ctx_builder = ContextBuilder(self)

        pm = PluginManager(
            plugins_dir=str(Path(root) / "plugins" / "violations"),
            foundational_dir=str(Path(root) / "plugins" / "foundational"),
            extensions_dir=str(Path(root) / "plugins" / "extensions"),
        )
        discovered = pm.discover_plugins(include_foundational=False)
        for name in discovered:
            pid = name.split(".")[-1]
            if pid in self.plugins or name in self.plugins:
                cfg = self.plugin_config.get(pid, self.plugin_config.get(name, {}))
                if pm.load_plugin(name, config=cfg):
                    if name not in pm.enabled_plugins:
                        pm.enabled_plugins.append(name)

        all_violations: List[dict] = []
        frame_index = 0
        last_detections: list = []

        while True:
            ret, frame = cap.read()
            if not ret:
                break
            if self.max_frames is not None and frame_index >= self.max_frames:
                break

            detections = detector.detect(frame)
            tracks = tracker.update(detections)
            for t in tracks:
                t.speed_mph = speed_est.update(t.track_id, t.position_history)

            for t in tracks:
                if t.frames_tracked < 3:
                    continue
                ctx = ctx_builder.build(t, frame, frame_index, fps)
                for plugin_id, plugin in pm.loaded_plugins.items():
                    if hasattr(plugin, "process_context"):
                        try:
                            results = plugin.process_context(ctx) or []
                            all_violations.extend(results)
                        except Exception as exc:
                            logger.debug("Plugin %s: %s", plugin_id, exc)

            frame_index += 1

        cap.release()

        # Evaluate assertions
        assertion_results: List[AssertionResult] = []
        for assertion in self.assertions:
            matching = [
                v for v in all_violations
                if v.get("type") == assertion.violation_type
                and (assertion.track_id is None or v.get("track_id") == assertion.track_id)
            ]
            count = len(matching)
            passed = count >= assertion.min_count
            if assertion.max_count is not None:
                passed = passed and count <= assertion.max_count
            msg = (
                f"{assertion.violation_type}: expected >={assertion.min_count}"
                + (f" and <={assertion.max_count}" if assertion.max_count else "")
                + f", got {count}"
            )
            assertion_results.append(AssertionResult(assertion, count, passed, msg))

        return ScenarioResult(
            scenario_name=self.name,
            total_violations=len(all_violations),
            violations=all_violations,
            assertion_results=assertion_results,
            all_passed=all(ar.passed for ar in assertion_results) if assertion_results else True,
        )
