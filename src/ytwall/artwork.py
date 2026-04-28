"""On-disk + in-memory cache for SoundCloud artwork.

Downloads (only once per URL) into ``%APPDATA%\\ytwall\\artwork\\<sha1>.jpg``
and caches a scaled QPixmap per (url, size) in memory.
"""
from __future__ import annotations

import hashlib
import logging
import threading
import urllib.request
from pathlib import Path

from PySide6.QtCore import QObject, QSize, Qt, QThread, Signal
from PySide6.QtGui import QPixmap

from .config import app_data_dir

log = logging.getLogger(__name__)
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


def _cache_dir() -> Path:
    d = app_data_dir() / "artwork"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _cache_path(url: str) -> Path:
    h = hashlib.sha1(url.encode("utf-8")).hexdigest()
    return _cache_dir() / f"{h}.jpg"


def download_blocking(url: str, timeout: float = 10.0) -> Path | None:
    """Download artwork synchronously; returns local path (or None on error)."""
    if not url:
        return None
    path = _cache_path(url)
    if path.exists() and path.stat().st_size > 0:
        return path
    try:
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = r.read()
        path.write_bytes(data)
        return path
    except Exception as e:  # noqa: BLE001
        log.debug("artwork download failed for %s: %s", url, e)
        return None


class ArtworkLoader(QObject):
    """Async artwork loader. Listeners connect to ``ready`` and emit a
    pixmap once the file is on disk."""

    ready = Signal(str, QPixmap)  # url, pixmap

    _instance: ArtworkLoader | None = None

    def __init__(self) -> None:
        super().__init__()
        self._mem: dict[tuple[str, int], QPixmap] = {}
        self._inflight: set[str] = set()
        self._lock = threading.Lock()

    @classmethod
    def instance(cls) -> ArtworkLoader:
        if cls._instance is None:
            cls._instance = ArtworkLoader()
        return cls._instance

    def request(self, url: str | None, size: QSize) -> QPixmap | None:
        """Synchronously return a scaled pixmap if available; otherwise
        kick off async fetch and return ``None``. Listeners receive the
        ``ready`` signal once the artwork is on disk."""
        if not url:
            return None
        key = (url, max(size.width(), size.height()))
        cached = self._mem.get(key)
        if cached is not None:
            return cached
        path = _cache_path(url)
        if path.exists() and path.stat().st_size > 0:
            pm = QPixmap(str(path))
            if not pm.isNull():
                pm = pm.scaled(
                    size,
                    Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                    Qt.TransformationMode.SmoothTransformation,
                )
                self._mem[key] = pm
                return pm
        # not on disk yet — fetch asynchronously
        with self._lock:
            if url in self._inflight:
                return None
            self._inflight.add(url)
        worker = _Worker(url, size, self)
        worker.start()
        return None


class _Worker(QThread):
    def __init__(self, url: str, size: QSize, parent: ArtworkLoader) -> None:
        super().__init__(parent)
        self._url = url
        self._size = size
        self._owner = parent

    def run(self) -> None:  # type: ignore[override]
        try:
            path = download_blocking(self._url)
            if not path:
                return
            pm = QPixmap(str(path))
            if pm.isNull():
                return
            scaled = pm.scaled(
                self._size,
                Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                Qt.TransformationMode.SmoothTransformation,
            )
            key = (self._url, max(self._size.width(), self._size.height()))
            self._owner._mem[key] = scaled
            self._owner.ready.emit(self._url, scaled)
        finally:
            with self._owner._lock:
                self._owner._inflight.discard(self._url)
