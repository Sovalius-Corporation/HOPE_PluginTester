"""TestSession — background thread that runs the full detection + plugin loop.

Pipeline per frame:
  VideoCapture → OnnxDetector → IoUTracker → SpeedEstimator
    → (optional) OnnxLPR  → ContextBuilder → plugin.process_context()
    → signals: frame_ready, violation_detected, stats_updated
"""
from __future__ import annotations

import logging
import sys
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Dict, List, Optional

import cv2
import numpy as np
from PySide6.QtCore import QThread, Signal

if TYPE_CHECKING:
    from scenarios.base import Scenario

logger = logging.getLogger(__name__)


class TestSession(QThread):
    """Runs in a background QThread; emits Qt signals back to the UI thread.

    Signals
    -------
    frame_ready(frame, tracks, violations)
        Emitted every processed frame.  ``frame`` is a BGR ``np.ndarray``,
        ``tracks`` a list of ``Track`` objects, ``violations`` a list of
        violation dicts produced by plugins this frame.
    violation_detected(dict)
        Fired once per individual violation event.
    stats_updated(dict)
        Emitted every 30 frames with processing metrics.
    session_error(str)
        Fatal error message.
    """

    frame_ready      = Signal(object, list, list)
    violation_detected = Signal(dict)
    stats_updated    = Signal(dict)
    session_error    = Signal(str)
    paused_changed   = Signal(bool)   # True = paused, False = running

    def __init__(self, scenario: "Scenario") -> None:
        super().__init__()
        self.scenario = scenario
        self._stop = False
        self._is_paused = False
        self._step_mode  = False
        self._pause_event = threading.Event()
        self._pause_event.set()   # set = running, clear = paused

    # ------------------------------------------------------------------
    # Control API  (called from the UI thread)
    # ------------------------------------------------------------------

    def stop(self) -> None:
        self._stop = True
        self._pause_event.set()   # unblock if paused so the thread can exit

    def pause(self) -> None:
        """Pause after the current frame completes."""
        self._is_paused = True
        self._step_mode  = False
        self._pause_event.clear()
        self.paused_changed.emit(True)

    def resume(self) -> None:
        """Resume continuous playback."""
        self._is_paused = False
        self._step_mode  = False
        self._pause_event.set()
        self.paused_changed.emit(False)

    def step(self) -> None:
        """Advance exactly one frame while staying paused."""
        if self._is_paused:
            self._step_mode = True
            self._pause_event.set()   # unblock for one frame

    # ------------------------------------------------------------------
    # QThread entry
    # ------------------------------------------------------------------

    def run(self) -> None:
        try:
            self._run_inner()
        except Exception as exc:
            logger.exception("Session fatal error")
            self.session_error.emit(str(exc))

    def _run_inner(self) -> None:
        from core.detector import OnnxDetector
        from core.speed_estimator import SpeedEstimator
        from core.tracker import IoUTracker

        scn = self.scenario

        # ── Plugin setup ─────────────────────────────────────────────
        # Mode A: SVG_HOPE root set → use SVG_HOPE PluginManager + ViolationContext
        # Mode B: plugins_dir set   → standalone loader, no SVG_HOPE needed
        # Mode C: neither           → detection+tracking only, plugins skipped

        svg_hope_root = str(scn.svg_hope_root).strip()
        plugins_dir   = str(getattr(scn, "plugins_dir", "")).strip()

        use_svg_hope   = bool(svg_hope_root)
        use_standalone = (not use_svg_hope) and bool(plugins_dir)

        pm = None                # SVG_HOPE PluginManager
        standalone_pm = None     # StandalonePluginLoader
        ctx_builder = None       # SVG_HOPE ContextBuilder (needs SVG_HOPE on path)

        if use_svg_hope:
            from core.context_builder import ContextBuilder

            root = str(Path(svg_hope_root).resolve())
            if root not in sys.path:
                sys.path.insert(0, root)

            from plugins.plugin_manager import PluginManager

            pm = PluginManager(
                plugins_dir=str(Path(root) / "plugins" / "violations"),
                foundational_dir=str(Path(root) / "plugins" / "foundational"),
                extensions_dir=str(Path(root) / "plugins" / "extensions"),
            )
            discovered = pm.discover_plugins(include_foundational=False)
            logger.info("Discovered plugins: %s", discovered)

            for name in discovered:
                plugin_id = name.split(".")[-1]
                if plugin_id in scn.plugins or name in scn.plugins:
                    cfg = scn.plugin_config.get(plugin_id, scn.plugin_config.get(name, {}))
                    if pm.load_plugin(name, config=cfg):
                        if name not in pm.enabled_plugins:
                            pm.enabled_plugins.append(name)
                        logger.info("Loaded plugin: %s  config=%s", name, cfg)
                    else:
                        logger.warning("Failed to load plugin: %s", name)

            logger.info("SVG_HOPE plugins ready: %d", len(pm.loaded_plugins))
            ctx_builder = ContextBuilder(scn)

        elif use_standalone:
            from core.standalone_loader import StandalonePluginLoader
            standalone_pm = StandalonePluginLoader(plugins_dir)
            standalone_pm.discover_and_load(scn.plugins, scn.plugin_config)
            logger.info("Standalone plugins ready: %s", standalone_pm.loaded_plugins)

        else:
            if scn.plugins:
                logger.warning(
                    "Plugins requested (%s) but neither svg_hope_root nor plugins_dir is set — "
                    "plugin evaluation skipped.  Set s.svg_hope_root (SVG_HOPE) or "
                    "s.plugins_dir (standalone .py files).",
                    scn.plugins,
                )
            else:
                logger.info("No plugins configured — detection + tracking only.")

        # ── Detector ─────────────────────────────────────────────────
        detector = OnnxDetector(
            scn.model_path,
            confidence_threshold=scn.confidence_threshold,
            device=getattr(scn, "device", "auto"),
        )
        active_providers = detector._sess.get_providers()
        logger.info("ONNX providers active: %s", active_providers)
        gpu_active = any(p in active_providers for p in ("CUDAExecutionProvider", "DmlExecutionProvider"))
        if not gpu_active:
            logger.warning(
                "Running on CPU (no GPU provider active). "
                "For NVIDIA: pip install onnxruntime-gpu. "
                "For AMD/Intel Radeon (DX12): pip install onnxruntime-directml — then set s.device='dml'."
            )

        # ── Video ────────────────────────────────────────────────────
        cap = cv2.VideoCapture(scn.video_path)
        if not cap.isOpened():
            raise RuntimeError(f"Cannot open video: {scn.video_path}")

        fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        logger.info("Video opened. fps=%.1f", fps)

        # ── Tracker + Speed ──────────────────────────────────────────
        tracker = IoUTracker()
        speed_est = SpeedEstimator(
            pixels_per_meter=scn.camera.pixels_per_meter,
            fps=fps,
        )

        # ── Optional LPR ─────────────────────────────────────────────
        lpr = None
        if scn.lpr_enabled and scn.lpr_model_path:
            try:
                from core.lpr import OnnxLPR
                lpr = OnnxLPR(scn.lpr_model_path)
                logger.info("LPR enabled")
            except Exception as exc:
                logger.warning("LPR init failed (continuing without): %s", exc)

        # --- Frame loop ---------------------------------------------
        frame_index = 0
        all_violations: List[dict] = []
        t0 = time.monotonic()
        stats_interval = 30
        frame_skip = max(1, getattr(scn, "frame_skip", 1))
        last_detections: List[dict] = []
        plugin_ema_ms: Dict[str, float] = {}   # per-plugin EMA latency (ms)

        while not self._stop:
            # ── pause / step gate ────────────────────────────────────
            self._pause_event.wait()   # blocks here when paused
            if self._stop:
                break
            if self._step_mode:
                # One-frame step: re-pause immediately after this frame
                self._step_mode = False
                self._pause_event.clear()
                self._is_paused = True

            ret, frame = cap.read()
            if not ret:
                break
            if scn.max_frames is not None and frame_index >= scn.max_frames:
                break

            ts = datetime.now()

            if frame_index % frame_skip == 0:
                last_detections = detector.detect(frame)
            detections = last_detections
            tracks = tracker.update(detections)

            # Speed estimation
            for t in tracks:
                t.speed_mph = speed_est.update(t.track_id, t.position_history)

            # LPR every 5 frames
            if lpr and frame_index % 5 == 0:
                for t in tracks:
                    text, conf = lpr.process(frame, t.bbox)
                    if text:
                        t.license_plate = text
                        t.plate_confidence = conf

            # ── Run plugins ──────────────────────────────────────────
            frame_violations: List[dict] = []

            if use_svg_hope and pm and ctx_builder:
                # SVG_HOPE mode: ViolationContext + PluginManager
                for t in tracks:
                    if t.frames_tracked < 3:
                        continue
                    ctx = ctx_builder.build(t, frame, frame_index, fps, ts)
                    for plugin_id, plugin in pm.loaded_plugins.items():
                        if not hasattr(plugin, "process_context"):
                            continue
                        try:
                            t_start = time.monotonic()
                            results = plugin.process_context(ctx) or []
                            ms = (time.monotonic() - t_start) * 1000.0
                            plugin_ema_ms[plugin_id] = (
                                0.1 * ms + 0.9 * plugin_ema_ms.get(plugin_id, ms)
                            )
                            for v in results:
                                v.setdefault("plugin_id", plugin_id)
                                v.setdefault("frame_index", frame_index)
                                thumb = cv2.resize(frame, (0, 0), fx=0.5, fy=0.5)
                                _, jpg = cv2.imencode(".jpg", thumb, [cv2.IMWRITE_JPEG_QUALITY, 82])
                                v["frame_snapshot"] = jpg.tobytes()
                                frame_violations.append(v)
                                all_violations.append(v)
                                self.violation_detected.emit(dict(v))
                        except Exception as exc:
                            logger.debug("Plugin %s error: %s", plugin_id, exc)

            elif use_standalone and standalone_pm:
                # Standalone mode: SimpleContext + StandalonePluginLoader
                from core.standalone_loader import SimpleContext, SimpleTrack
                for t in tracks:
                    if t.frames_tracked < 3:
                        continue
                    st = SimpleTrack(
                        track_id=t.track_id,
                        bbox=t.bbox,
                        vehicle_type=getattr(t, "vehicle_type", "car"),
                        speed_mph=t.speed_mph,
                        license_plate=getattr(t, "license_plate", ""),
                        confidence=getattr(t, "confidence", 0.0),
                        position_history=list(t.position_history),
                    )
                    ctx = SimpleContext(
                        track=st,
                        camera=scn.camera,
                        lanes=scn.lanes,
                        frame=frame,
                        frame_index=frame_index,
                        fps=fps,
                        timestamp=ts,
                    )
                    plugin_results = standalone_pm.run_plugins(ctx)
                    for plugin_id, results in plugin_results.items():
                        t_start = time.monotonic()
                        ms = (time.monotonic() - t_start) * 1000.0
                        plugin_ema_ms[plugin_id] = (
                            0.1 * ms + 0.9 * plugin_ema_ms.get(plugin_id, ms)
                        )
                        for v in results:
                            v.setdefault("plugin_id", plugin_id)
                            v.setdefault("frame_index", frame_index)
                            v.setdefault("track_id", t.track_id)
                            thumb = cv2.resize(frame, (0, 0), fx=0.5, fy=0.5)
                            _, jpg = cv2.imencode(".jpg", thumb, [cv2.IMWRITE_JPEG_QUALITY, 82])
                            v["frame_snapshot"] = jpg.tobytes()
                            frame_violations.append(v)
                            all_violations.append(v)
                            self.violation_detected.emit(dict(v))

            self.frame_ready.emit(frame, list(tracks), frame_violations)

            frame_index += 1
            if frame_index % stats_interval == 0:
                elapsed = time.monotonic() - t0
                self.stats_updated.emit({
                    "frame_index": frame_index,
                    "elapsed_sec": elapsed,
                    "processing_fps": round(frame_index / elapsed, 1) if elapsed > 0 else 0,
                    "total_violations": len(all_violations),
                    "active_tracks": len(tracks),
                    "plugin_latency_ms": dict(plugin_ema_ms),
                })

        cap.release()
        logger.info(
            "Session complete. frames=%d  violations=%d",
            frame_index, len(all_violations),
        )
