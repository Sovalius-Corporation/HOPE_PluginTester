"""Standalone plugin loader — works without any SVG_HOPE installation.

Plugins in the chosen directory must expose a module-level function::

    def process_context(ctx) -> list[dict]:
        ...

where *ctx* is a :class:`SimpleContext` that mirrors the key attributes of
SVG_HOPE's ``ViolationContext`` so well-written plugins are compatible with
both environments.

Return value: a list of violation dicts (same schema as SVG_HOPE plugins):
    {
        "type": str,          # violation identifier, e.g. "speeding"
        "severity": str,      # "low" | "medium" | "high" | "critical"
        "track_id": int,
        "speed_mph": float,   # optional
        "details": str,       # optional
    }
"""
from __future__ import annotations

import importlib.util
import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from types import ModuleType
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# SimpleContext  — duck-type compatible with SVG_HOPE ViolationContext
# ---------------------------------------------------------------------------

@dataclass
class SimpleTrack:
    """Minimal track proxy forwarded to standalone plugins."""
    track_id: int
    bbox: tuple                  # (x1, y1, x2, y2)
    vehicle_type: str = "car"
    speed_mph: float = 0.0
    license_plate: str = ""
    confidence: float = 0.0
    position_history: list = field(default_factory=list)


class SimpleContext:
    """Lightweight ViolationContext shim for standalone (non-SVG_HOPE) plugins.

    Attribute access matches the SVG_HOPE ViolationContext interface so plugins
    written against SVG_HOPE will also work here as long as they only touch the
    fields below.  Missing SVG_HOPE-specific helpers (e.g. ``get_vehicle_lane``)
    return safe defaults instead of raising.
    """

    def __init__(
        self,
        track: SimpleTrack,
        camera,           # scenarios.base.Camera
        lanes: list,      # list[scenarios.base.Lane]
        frame,            # np.ndarray BGR
        frame_index: int,
        fps: float,
        timestamp: Optional[datetime] = None,
    ) -> None:
        self.track = track
        self.camera = camera
        self.lanes = lanes
        self.frame = frame
        self.frame_index = frame_index
        self.fps = fps
        self.timestamp = timestamp or datetime.now()

        # Mimic commonly accessed SVG_HOPE ViolationContext attributes
        self.camera_name: str = getattr(camera, "name", "cam1")
        self.speed_limit_mph: int = getattr(camera, "speed_limit_mph", 30)
        self.pixels_per_meter: float = getattr(camera, "pixels_per_meter", 10.0)
        self.is_built_up_area: bool = getattr(camera, "is_built_up_area", True)
        self.country_code: str = getattr(camera, "country_code", "US")

    # ------------------------------------------------------------------
    # SVG_HOPE ViolationContext interface shims
    # ------------------------------------------------------------------

    def get_vehicle_lane(self, hysteresis: int = 3) -> Optional[Any]:
        """Return the lane containing this track's bounding-box centre, or None."""
        cx = (self.track.bbox[0] + self.track.bbox[2]) / 2
        cy = (self.track.bbox[1] + self.track.bbox[3]) / 2
        for lane in self.lanes:
            if _point_in_polygon((cx, cy), getattr(lane, "boundaries", [])):
                return lane
        return None

    def get_current_speed_mph(self) -> float:
        return self.track.speed_mph

    def get_speed_limit_mph(self) -> int:
        lane = self.get_vehicle_lane()
        if lane is not None:
            lim = getattr(lane, "speed_limit_mph", None)
            if lim is not None:
                return lim
        return self.speed_limit_mph

    # Forward unknown attribute access gracefully
    def __getattr__(self, name: str) -> Any:
        logger.debug("SimpleContext: unknown attribute %r — returning None", name)
        return None


def _point_in_polygon(pt, poly) -> bool:
    """Ray-casting test."""
    x, y = pt
    n = len(poly)
    inside = False
    j = n - 1
    for i in range(n):
        xi, yi = poly[i]
        xj, yj = poly[j]
        if ((yi > y) != (yj > y)) and (x < (xj - xi) * (y - yi) / (yj - yi + 1e-9) + xi):
            inside = not inside
        j = i
    return inside


# ---------------------------------------------------------------------------
# StandalonePluginLoader
# ---------------------------------------------------------------------------

class StandalonePluginLoader:
    """Loads .py plugin files from a directory and calls process_context()."""

    def __init__(self, plugins_dir: str) -> None:
        self._dir = Path(plugins_dir)
        self._plugins: Dict[str, ModuleType] = {}
        self.loaded_plugins: List[str] = []
        self.enabled_plugins: List[str] = []

    def discover_and_load(
        self,
        requested: List[str],
        config: Dict[str, dict],
    ) -> None:
        """Load plugins whose stem is in *requested* from the plugins directory."""
        if not self._dir.is_dir():
            logger.warning("plugins_dir not found: %s", self._dir)
            return

        for fpath in sorted(self._dir.glob("*.py")):
            if fpath.name.startswith("_"):
                continue
            pid = fpath.stem
            if pid not in requested:
                continue
            try:
                spec = importlib.util.spec_from_file_location(pid, fpath)
                mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)   # type: ignore[union-attr]

                # Pass config if the module exposes configure()
                cfg = config.get(pid, {})
                if hasattr(mod, "configure") and callable(mod.configure):
                    mod.configure(cfg)

                self._plugins[pid] = mod
                self.loaded_plugins.append(pid)
                self.enabled_plugins.append(pid)
                logger.info("Standalone: loaded plugin %s from %s", pid, fpath)
            except Exception as exc:
                logger.warning("Standalone: failed to load %s: %s", pid, exc)

    def run_plugins(
        self,
        ctx: SimpleContext,
    ) -> Dict[str, List[dict]]:
        """Run all enabled plugins against *ctx*.

        Returns ``{plugin_id: [violation_dict, ...]}``.
        """
        results: Dict[str, List[dict]] = {}
        for pid in self.enabled_plugins:
            mod = self._plugins.get(pid)
            if mod is None:
                continue
            fn = getattr(mod, "process_context", None)
            if fn is None:
                logger.warning("Plugin %s has no process_context()", pid)
                continue
            try:
                out = fn(ctx) or []
                results[pid] = list(out)
            except Exception as exc:
                logger.debug("Standalone plugin %s error: %s", pid, exc)
                results[pid] = []
        return results
