"""GitHubPanel -- browse a GitHub repository and download plugin .py files.

Fetches the directory listing from the GitHub Contents API (no auth required
for public repos) and lets the user check-select files to download into a
local plugins directory.

A personal access token can be entered for private repos or to raise the
rate-limit from 60 to 5 000 requests/hour.
"""
from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.request
from typing import List, Optional, Tuple

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Background threads
# ---------------------------------------------------------------------------

class _FetchThread(QThread):
    fetched = Signal(list)   # list of (name: str, download_url: str)
    error   = Signal(str)

    def __init__(self, repo: str, path: str, token: str) -> None:
        super().__init__()
        self._repo  = repo.strip().strip("/")
        self._path  = path.strip().strip("/")
        self._token = token.strip()

    def run(self) -> None:
        url = f"https://api.github.com/repos/{self._repo}/contents/{self._path}"
        req = urllib.request.Request(url)
        req.add_header("Accept", "application/vnd.github.v3+json")
        req.add_header("User-Agent", "HOPEPluginTester/1.0")
        if self._token:
            req.add_header("Authorization", f"token {self._token}")
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            self.error.emit(f"HTTP {e.code}: {e.reason}")
            return
        except Exception as e:
            self.error.emit(str(e))
            return

        if not isinstance(data, list):
            self.error.emit("Unexpected response — is the path a directory?")
            return

        files = [
            (item["name"], item["download_url"])
            for item in data
            if item.get("type") == "file"
            and item["name"].endswith(".py")
            and not item["name"].startswith("_")
        ]
        self.fetched.emit(files)


class _DownloadThread(QThread):
    progress  = Signal(int, int)   # done, total
    log_line  = Signal(str)
    finished_ = Signal(int)        # files downloaded

    def __init__(self, files: List[Tuple[str, str]], dest: str, token: str) -> None:
        super().__init__()
        self._files = files
        self._dest  = dest
        self._token = token.strip()

    def run(self) -> None:
        os.makedirs(self._dest, exist_ok=True)
        done = 0
        for i, (name, url) in enumerate(self._files, 1):
            try:
                req = urllib.request.Request(url)
                req.add_header("User-Agent", "HOPEPluginTester/1.0")
                if self._token:
                    req.add_header("Authorization", f"token {self._token}")
                with urllib.request.urlopen(req, timeout=20) as resp:
                    content = resp.read()
                dest_path = os.path.join(self._dest, name)
                with open(dest_path, "wb") as f:
                    f.write(content)
                self.log_line.emit(f"  Downloaded: {name}")
                done += 1
            except Exception as e:
                self.log_line.emit(f"  FAILED {name}: {e}")
            self.progress.emit(i, len(self._files))
        self.finished_.emit(done)


# ---------------------------------------------------------------------------
# Panel widget
# ---------------------------------------------------------------------------

class GitHubPanel(QWidget):
    """Browse a GitHub repo for plugin .py files and download them locally."""

    plugins_downloaded = Signal(str)   # dest dir, for auto-populating scenario panel

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._checkboxes: List[Tuple[QCheckBox, str, str]] = []   # (cb, name, url)
        self._fetch_thread: Optional[_FetchThread] = None
        self._dl_thread: Optional[_DownloadThread] = None

        # ── Source ─────────────────────────────────────────────────────
        src = QGroupBox("Source Repository")
        sf  = QVBoxLayout(src)
        sf.setSpacing(4)

        r1 = QHBoxLayout()
        r1.addWidget(QLabel("Repo:"))
        self._repo = QLineEdit()
        self._repo.setPlaceholderText("org/repo  e.g. Sovalius-Corporation/HOPE_PluginTester")
        r1.addWidget(self._repo)
        sf.addLayout(r1)

        r2 = QHBoxLayout()
        r2.addWidget(QLabel("Path:"))
        self._path = QLineEdit("plugins/violations")
        r2.addWidget(self._path)
        sf.addLayout(r2)

        r3 = QHBoxLayout()
        r3.addWidget(QLabel("Token:"))
        self._token = QLineEdit()
        self._token.setPlaceholderText("Optional — needed for private repos / higher rate-limit")
        self._token.setEchoMode(QLineEdit.EchoMode.Password)
        r3.addWidget(self._token)
        sf.addLayout(r3)

        self._fetch_btn = QPushButton("Fetch File List")
        self._fetch_btn.setObjectName("primary")
        sf.addWidget(self._fetch_btn)

        # ── File list ──────────────────────────────────────────────────
        lst = QGroupBox("Available Plugins")
        lf  = QVBoxLayout(lst)

        sel_row = QHBoxLayout()
        self._status_lbl = QLabel("Enter a repo and click Fetch.")
        self._status_lbl.setStyleSheet("color:#94a3b8;font-size:10px;")
        sel_row.addWidget(self._status_lbl, stretch=1)
        all_btn  = QPushButton("All")
        none_btn = QPushButton("None")
        all_btn.setFixedWidth(46)
        none_btn.setFixedWidth(46)
        all_btn.clicked.connect(lambda: [cb.setChecked(True)  for cb, _, __ in self._checkboxes])
        none_btn.clicked.connect(lambda: [cb.setChecked(False) for cb, _, __ in self._checkboxes])
        sel_row.addWidget(all_btn)
        sel_row.addWidget(none_btn)
        lf.addLayout(sel_row)

        self._cb_inner = QWidget()
        self._cb_layout = QVBoxLayout(self._cb_inner)
        self._cb_layout.setSpacing(3)
        self._cb_layout.setContentsMargins(4, 4, 4, 4)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setWidget(self._cb_inner)
        scroll.setMinimumHeight(130)
        lf.addWidget(scroll)

        # ── Destination ────────────────────────────────────────────────
        dst = QGroupBox("Download To")
        df  = QVBoxLayout(dst)

        dest_row = QHBoxLayout()
        self._dest = QLineEdit()
        self._dest.setPlaceholderText(r"D:\my_plugins" + "\\")
        browse_btn = QPushButton("...")
        browse_btn.setFixedSize(28, 26)
        browse_btn.clicked.connect(self._pick_dest)
        dest_row.addWidget(self._dest)
        dest_row.addWidget(browse_btn)
        df.addLayout(dest_row)

        self._progress = QProgressBar()
        self._progress.setVisible(False)
        df.addWidget(self._progress)

        self._log_lbl = QLabel("")
        self._log_lbl.setStyleSheet("color:#86efac;font-size:10px;")
        self._log_lbl.setWordWrap(True)
        df.addWidget(self._log_lbl)

        self._dl_btn = QPushButton("Download Selected")
        self._dl_btn.setObjectName("primary")
        self._dl_btn.setEnabled(False)
        df.addWidget(self._dl_btn)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)
        layout.addWidget(src)
        layout.addWidget(lst, stretch=1)
        layout.addWidget(dst)

        self._fetch_btn.clicked.connect(self._on_fetch)
        self._dl_btn.clicked.connect(self._on_download)

    # ------------------------------------------------------------------

    def _pick_dest(self) -> None:
        p = QFileDialog.getExistingDirectory(self, "Select destination folder", self._dest.text())
        if p:
            self._dest.setText(p)

    def _clear_list(self) -> None:
        self._checkboxes.clear()
        while self._cb_layout.count():
            item = self._cb_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    # ------------------------------------------------------------------
    # Fetch
    # ------------------------------------------------------------------

    def _on_fetch(self) -> None:
        repo = self._repo.text().strip()
        if not repo:
            self._status_lbl.setText("Enter a repository (org/repo) first.")
            return
        self._clear_list()
        self._dl_btn.setEnabled(False)
        self._fetch_btn.setEnabled(False)
        self._status_lbl.setText(f"Fetching {repo}/{self._path.text().strip()} ...")

        self._fetch_thread = _FetchThread(repo, self._path.text(), self._token.text())
        self._fetch_thread.fetched.connect(self._on_fetched)
        self._fetch_thread.error.connect(self._on_fetch_error)
        self._fetch_thread.start()

    def _on_fetched(self, files: list) -> None:
        self._fetch_btn.setEnabled(True)
        if not files:
            self._status_lbl.setText("No .py files found at that path.")
            return
        self._status_lbl.setText(f"Found {len(files)} plugin file(s).")
        for name, url in files:
            cb = QCheckBox(name)
            cb.setChecked(True)
            self._cb_layout.addWidget(cb)
            self._checkboxes.append((cb, name, url))
        self._cb_layout.addStretch()
        self._dl_btn.setEnabled(True)

    def _on_fetch_error(self, msg: str) -> None:
        self._fetch_btn.setEnabled(True)
        self._status_lbl.setText(f"Error: {msg}")

    # ------------------------------------------------------------------
    # Download
    # ------------------------------------------------------------------

    def _on_download(self) -> None:
        dest = self._dest.text().strip()
        if not dest:
            self._status_lbl.setText("Set a destination folder first.")
            return
        selected = [(name, url) for cb, name, url in self._checkboxes if cb.isChecked()]
        if not selected:
            self._status_lbl.setText("No files selected.")
            return

        self._progress.setMaximum(len(selected))
        self._progress.setValue(0)
        self._progress.setVisible(True)
        self._dl_btn.setEnabled(False)
        self._log_lbl.setText("")

        self._dl_thread = _DownloadThread(selected, dest, self._token.text())
        self._dl_thread.progress.connect(lambda d, _: self._progress.setValue(d))
        self._dl_thread.log_line.connect(
            lambda s: self._log_lbl.setText(self._log_lbl.text() + "\n" + s)
        )
        self._dl_thread.finished_.connect(self._on_dl_done)
        self._dl_thread.start()

    def _on_dl_done(self, count: int) -> None:
        self._dl_btn.setEnabled(True)
        self._status_lbl.setText(f"Done -- {count} file(s) downloaded.")
        dest = self._dest.text().strip()
        if dest and count > 0:
            self.plugins_downloaded.emit(dest)
