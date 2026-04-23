# -*- mode: python ; coding: utf-8 -*-
#
# PyInstaller spec — SINGLE FILE (portable, no install needed)
#
# Build:
#   cd D:\Projects\hope_plugin_tester
#   py -m PyInstaller hope_plugin_tester_onefile.spec --noconfirm
#
# Output: dist\HOPEPluginTester.exe  (single portable exe, ~70 MB)
#
# NOTE: On first launch the exe extracts itself to %TEMP%\MEI... — this is
# normal PyInstaller behaviour. Subsequent launches reuse the same temp folder
# so startup is faster. The temp folder is cleaned up on exit.

import os
from pathlib import Path

block_cipher = None

HERE = Path(SPECPATH)  # noqa: F821

a = Analysis(
    [str(HERE / "main.py")],
    pathex=[str(HERE)],
    binaries=[],
    datas=[
        (str(HERE / "config" / "example_camera.json"), "config"),
        (str(HERE / "scenarios" / "example_speeding.py"), "scenarios"),
    ],
    hiddenimports=[
        "onnxruntime.capi._pybind_state",
        "cv2",
        "numpy",
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
        "gi", "pyds", "tensorrt", "torch", "torchvision",
        "matplotlib", "scipy", "pandas", "IPython",
        "notebook", "jupyter", "tkinter", "_tkinter", "wx",
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)  # noqa: F821

# ---------------------------------------------------------------------------
# Single-file EXE — everything packed into one portable executable
# ---------------------------------------------------------------------------
exe = EXE(  # noqa: F821
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="HOPEPluginTester",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,          # UPX can corrupt ONNX Runtime DLLs — keep off
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,      # no console window
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    # icon=str(HERE / "assets" / "icon.ico"),
)
