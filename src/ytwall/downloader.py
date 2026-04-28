from __future__ import annotations

import os
import re
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QObject, QRunnable, Signal


def _bundled_ffmpeg_dir() -> str | None:
    """Return the directory containing ffmpeg.exe / ffprobe.exe shipped with us.

    Search order:
      1. PyInstaller _MEIPASS (when running from the frozen .exe)
      2. Directory next to the running executable (`sys.executable`'s parent)
      3. Repo-root `bin/` (development mode)
      4. None — fall back to system PATH (yt-dlp's default).
    """
    candidates: list[Path] = []
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        candidates.append(Path(meipass))
        candidates.append(Path(meipass) / "bin")
    if getattr(sys, "frozen", False):
        candidates.append(Path(sys.executable).parent)
        candidates.append(Path(sys.executable).parent / "bin")
    candidates.append(Path(__file__).resolve().parent.parent.parent / "bin")

    for d in candidates:
        if (d / "ffmpeg.exe").exists() or (d / "ffmpeg").exists():
            return str(d)

    found = shutil.which("ffmpeg")
    if found:
        return str(Path(found).parent)
    return None


def has_ffmpeg() -> bool:
    return _bundled_ffmpeg_dir() is not None

_QUALITY_MAP = {
    "720p": "bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/best[height<=720][ext=mp4]/best",
    "1080p": "bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/best[height<=1080][ext=mp4]/best",
    "1440p": "bestvideo[height<=1440][ext=mp4]+bestaudio[ext=m4a]/best[height<=1440][ext=mp4]/best",
    "2160p": "bestvideo[height<=2160][ext=mp4]+bestaudio[ext=m4a]/best[height<=2160][ext=mp4]/best",
    "best": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
}


def quality_format(quality: str) -> str:
    return _QUALITY_MAP.get(quality, _QUALITY_MAP["1080p"])


YOUTUBE_RE = re.compile(
    r"(?:https?://)?(?:www\.|m\.|music\.)?(?:youtube\.com|youtu\.be)/", re.I
)


def is_youtube_url(s: str) -> bool:
    return bool(YOUTUBE_RE.search((s or "").strip()))


@dataclass
class DownloadResult:
    file: str
    thumbnail: str | None
    title: str
    artist: str
    duration: float
    width: int
    height: int
    url: str


class DownloadSignals(QObject):
    progress = Signal(float, str)  # 0..1, status message
    finished = Signal(object)  # DownloadResult
    failed = Signal(str)  # error message
    log = Signal(str)


class DownloadJob(QRunnable):
    """Run a yt-dlp download in a worker thread.

    Emits progress signals on the main thread via Qt signals.
    """

    def __init__(self, url: str, dest_dir: Path, quality: str = "1080p") -> None:
        super().__init__()
        self.url = url.strip()
        self.dest_dir = Path(dest_dir)
        self.quality = quality
        self.signals = DownloadSignals()
        self._cancel = False

    def cancel(self) -> None:
        self._cancel = True

    # ---- yt-dlp callback ----
    def _hook(self, d: dict) -> None:
        if self._cancel:
            raise _Cancelled()
        status = d.get("status")
        if status == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
            done = d.get("downloaded_bytes") or 0
            frac = (done / total) if total else 0.0
            speed = d.get("speed") or 0
            speed_mb = (speed / 1024 / 1024) if speed else 0
            eta = d.get("eta") or 0
            msg = f"Загрузка… {frac * 100:5.1f}%  {speed_mb:5.2f} MB/s  ETA {int(eta)}s"
            self.signals.progress.emit(frac, msg)
        elif status == "finished":
            self.signals.progress.emit(1.0, "Постобработка (mux)…")
        elif status == "error":
            self.signals.log.emit("yt-dlp reported an error during download")

    def run(self) -> None:  # type: ignore[override]
        try:
            self._run()
        except _Cancelled:
            self.signals.failed.emit("Загрузка отменена")
        except Exception as e:  # noqa: BLE001
            self.signals.failed.emit(f"{type(e).__name__}: {e}")

    def _run(self) -> None:
        if not is_youtube_url(self.url):
            raise ValueError("Это не похоже на ссылку YouTube")

        try:
            from yt_dlp import YoutubeDL
        except ImportError as e:  # pragma: no cover
            raise RuntimeError(
                "yt-dlp is not installed. Install with: pip install yt-dlp"
            ) from e

        self.dest_dir.mkdir(parents=True, exist_ok=True)

        outtmpl = str(self.dest_dir / "%(title).80B [%(id)s].%(ext)s")
        opts = {
            "format": quality_format(self.quality),
            "outtmpl": outtmpl,
            "merge_output_format": "mp4",
            "writethumbnail": True,
            "noprogress": True,
            "quiet": True,
            "no_warnings": True,
            "progress_hooks": [self._hook],
            "postprocessors": [
                {"key": "FFmpegThumbnailsConvertor", "format": "jpg"},
            ],
            "concurrent_fragment_downloads": 4,
            "retries": 5,
        }

        ffmpeg_dir = _bundled_ffmpeg_dir()
        if ffmpeg_dir:
            opts["ffmpeg_location"] = ffmpeg_dir
            # also extend PATH so any sub-tool yt-dlp spawns finds ffprobe
            os.environ["PATH"] = ffmpeg_dir + os.pathsep + os.environ.get("PATH", "")

        self.signals.progress.emit(0.0, "Извлечение метаданных…")

        with YoutubeDL(opts) as ydl:
            info = ydl.extract_info(self.url, download=True)

        if isinstance(info, dict) and info.get("_type") == "playlist":
            entries = info.get("entries") or []
            if not entries:
                raise RuntimeError("Плейлист пуст")
            info = entries[0]

        # Resolve final file path
        file_path: str | None = None
        if info.get("requested_downloads"):
            file_path = info["requested_downloads"][0].get("filepath")
        if not file_path:
            file_path = info.get("filepath") or info.get("_filename")
        if not file_path or not Path(file_path).exists():
            # Fall back: search by id in dest dir
            video_id = info.get("id") or ""
            for p in self.dest_dir.iterdir():
                if video_id and video_id in p.name and p.suffix.lower() in {".mp4", ".mkv", ".webm"}:
                    file_path = str(p)
                    break
        if not file_path:
            raise RuntimeError("Не удалось определить путь к скачанному файлу")

        thumb_path: str | None = None
        base = Path(file_path).with_suffix("")
        for ext in (".jpg", ".png", ".webp"):
            candidate = base.with_suffix(ext)
            if candidate.exists():
                thumb_path = str(candidate)
                break

        result = DownloadResult(
            file=file_path,
            thumbnail=thumb_path,
            title=info.get("title") or Path(file_path).stem,
            artist=info.get("uploader") or info.get("channel") or "",
            duration=float(info.get("duration") or 0.0),
            width=int(info.get("width") or 0),
            height=int(info.get("height") or 0),
            url=info.get("webpage_url") or self.url,
        )
        self.signals.progress.emit(1.0, "Готово")
        self.signals.finished.emit(result)


class _Cancelled(Exception):
    pass
