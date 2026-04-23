# -*- mode: python ; coding: utf-8 -*-
#
# PyInstaller spec file for HOPE Plugin Tester
#
# Build:
#   cd D:\Projects\hope_plugin_tester
#   pip install pyinstaller
#   pyinstaller hope_plugin_tester.spec
#
# Output: dist\HOPEPluginTester\HOPEPluginTester.exe  (folder mode, faster startup)
#
# NOTE: The exe does NOT bundle SVG_HOPE plugins — it resolves them at runtime
# from SVG_HOPE_ROOT (set via the UI or environment variable).

import os
from pathlib import Path

block_cipher = None

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
HERE = Path(SPECPATH)  # noqa: F821  (SPECPATH injected by PyInstaller)

# ---------------------------------------------------------------------------
# Analysis
# ---------------------------------------------------------------------------
a = Analysis(
    [str(HERE / "main.py")],
    pathex=[str(HERE)],
    binaries=[],
    datas=[
        # Bundle the example config so the exe ships with it
        (str(HERE / "config" / "example_camera.json"), "config"),
        # Bundle scenario examples
        (str(HERE / "scenarios" / "example_speeding.py"), "scenarios"),
    ],
    hiddenimports=[
        # ONNX Runtime providers
        "onnxruntime.capi._pybind_state",
        # OpenCV
        "cv2",
        # numpy
        "numpy",
        # Our own packages
        "core",
        "core.detector",
        "core.tracker",
        "core.speed_estimator",
        "core.lpr",
        "core.context_builder",
        "core.session",
        "ui",
        "ui.app",
        "ui.video_panel",
        "ui.plugin_panel",
        "ui.violations_panel",
        "ui.scenario_panel",
        "scenarios",
        "scenarios.base",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # Exclude heavy packages that are definitely not needed
        "gi",
        "pyds",
        "tensorrt",
        "torch",
        "torchvision",
        "matplotlib",
        "scipy",
        "pandas",
        "IPython",
        "notebook",
        "jupyter",
        "tkinter",
        "_tkinter",
        "wx",
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)  # noqa: F821

# ---------------------------------------------------------------------------
# EXE — one-folder mode (faster cold start, easier to update ONNX models)
# ---------------------------------------------------------------------------
exe = EXE(  # noqa: F821
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="HOPEPluginTester",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,          # UPX can corrupt ONNX Runtime DLLs
    console=False,      # no console window
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    # icon=str(HERE / "assets" / "icon.ico"),  # uncomment if you add an icon
)

coll = COLLECT(  # noqa: F821
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="HOPEPluginTester",
)
