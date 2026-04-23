"""Example scenario: Speeding detection.

Edit the three path constants at the top, then run::

    python scenarios/example_speeding.py

Or paste the contents into the Script tab of the UI.
"""
import os
import sys

# -----------------------------------------------------------------------
# EDIT THESE PATHS
# -----------------------------------------------------------------------
SVG_HOPE_ROOT = r"D:\Projects\SVG_HOPE"
VIDEO_PATH    = r"D:\videos\test_highway.mp4"   # any mp4/avi with vehicles
MODEL_PATH    = os.path.join(SVG_HOPE_ROOT, "models", "yolov8n.onnx")
# -----------------------------------------------------------------------

# Make sure the tester package itself is importable when run standalone
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scenarios.base import Camera, Lane, Scenario, ViolationAssertion

s = Scenario("speeding_low_limit")
s.svg_hope_root = SVG_HOPE_ROOT
s.video_path    = VIDEO_PATH
s.model_path    = MODEL_PATH

# ---- Plugins ----
s.plugins = ["speeding"]
s.plugin_config = {
    "speeding": {
        "tolerance_mph":      0,    # no tolerance — any excess fires
        "min_duration_sec":   1.0,  # confirm after 1 second (default is 2s)
        "min_frames_tracked": 5,    # stable tracks only (default 15)
    }
}

# ---- Camera ----
# pixels_per_meter: measure a known distance in the video frame to calibrate.
# 8.5 px/m is typical for a medium-height overhead camera at 720p.
s.camera = Camera(
    name="highway_cam",
    speed_limit_mph=5,          # artificially low to guarantee detections
    pixels_per_meter=8.5,
    location="Test Intersection",
    country_code="US",
)

# ---- Lanes ----
# Cover the full 1280×720 frame so every tracked vehicle is "in lane".
# Replace with real lane polygon coordinates from your calibration tool.
s.lanes = [
    Lane(
        lane_id=0,
        boundaries=[(0, 0), (1280, 0), (1280, 720), (0, 720)],
        direction_angle=0.0,
        speed_limit_mph=5,
        name="full_frame_lane",
    )
]

# ---- Assertions ----
s.assertions = [
    ViolationAssertion("speeding", min_count=1),
]

# -----------------------------------------------------------------------
if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    print(f"Scenario : {s.name}")
    print(f"Video    : {s.video_path}")
    print(f"Model    : {s.model_path}")
    print(f"Plugins  : {s.plugins}")
    print()

    result = s.run()
    print(result.summary())
    sys.exit(0 if result.all_passed else 1)
