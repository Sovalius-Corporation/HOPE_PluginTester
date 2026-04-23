"""HotReloader -- QFileSystemWatcher-based live plugin reload.

Wire up:
    reloader = HotReloader(parent=app)
    reloader.watch(plugins_dir)
    reloader.plugin_changed.connect(session.request_plugin_reload)
"""
from __future__ import annotations

import logging
from pathlib import Path

from PySide6.QtCore import QFileSystemWatcher, QObject, Signal

logger = logging.getLogger(__name__)


class HotReloader(QObject):
    """Watches a plugin directory; emits plugin_changed(path) on .py file saves."""

    plugin_changed = Signal(str)   # absolute path of changed .py (empty = dir rescan)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._watcher = QFileSystemWatcher(self)
        self._watcher.fileChanged.connect(self._on_file)
        self._watcher.directoryChanged.connect(self._on_dir)
        self._dir = ""
        self._active = False

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def watch(self, directory: str) -> None:
        """Start watching all .py files (and the directory itself) for changes."""
        self._stop()
        if not directory:
            return
        self._dir = directory
        self._watcher.addPath(directory)
        for p in Path(directory).glob("*.py"):
            if not p.name.startswith("_"):
                self._watcher.addPath(str(p))
        self._active = True
        count = len(self._watcher.files())
        logger.info("HotReloader: watching %d files in %s", count, directory)

    def stop(self) -> None:
        self._stop()

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _stop(self) -> None:
        if self._watcher.files():
            self._watcher.removePaths(self._watcher.files())
        if self._watcher.directories():
            self._watcher.removePaths(self._watcher.directories())
        self._dir = ""
        self._active = False

    def _on_file(self, path: str) -> None:
        # Some file-systems remove the watch after a write; re-add it
        if path not in self._watcher.files():
            self._watcher.addPath(path)
        logger.info("HotReloader: changed -> %s", path)
        self.plugin_changed.emit(path)

    def _on_dir(self, directory: str) -> None:
        """Pick up newly created .py files in the watched directory."""
        existing = set(self._watcher.files())
        for p in Path(directory).glob("*.py"):
            if not p.name.startswith("_") and str(p) not in existing:
                self._watcher.addPath(str(p))
                logger.info("HotReloader: new file detected -> %s", p)
        self.plugin_changed.emit("")   # signal a rescan
