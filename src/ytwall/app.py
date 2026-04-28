"""Application bootstrap and top-level controller."""

from __future__ import annotations

import logging
import sys
from pathlib import Path

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QGuiApplication, QIcon, QPixmap
from PySide6.QtWidgets import QApplication, QMessageBox

from .config import Settings, app_data_dir
from .library import Library
from .music_player import MusicPlayer
from .pause_monitor import PauseMonitor
from .playlists import Playlists
from .soundcloud import SoundCloudClient
from .styles import QSS
from .tray import Tray
from .wallpaper import WallpaperEngine
from .widgets.main_window import MainWindow

log = logging.getLogger(__name__)


def _configure_logging() -> None:
    log_path = app_data_dir() / "ytwall.log"
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=[
            logging.FileHandler(log_path, encoding="utf-8"),
            logging.StreamHandler(sys.stdout),
        ],
    )


def _build_app_icon() -> QIcon:
    candidates = [
        Path(__file__).resolve().parent.parent.parent / "assets" / "icon.png",
        Path(getattr(sys, "_MEIPASS", "")) / "assets" / "icon.png" if getattr(sys, "_MEIPASS", "") else None,
    ]
    for c in candidates:
        if c and c.exists():
            return QIcon(str(c))
    pix = QPixmap(QSize(64, 64))
    pix.fill(Qt.transparent)
    return QIcon(pix)


class Controller:
    """Wires the UI with the wallpaper engine and pause monitor."""

    def __init__(self, app: QApplication) -> None:
        self.app = app
        self.settings = Settings.load()
        self.library = Library()
        self.playlists = Playlists()
        self.sc = SoundCloudClient(cache_path=app_data_dir() / "sc-client-id.json")
        self.player = MusicPlayer(self.sc)
        self.engine = WallpaperEngine()
        self.monitor = PauseMonitor(
            pause_on_fullscreen=self.settings.pause_on_fullscreen,
            pause_on_battery=self.settings.pause_on_battery,
            pause_when_obscured=self.settings.pause_when_obscured,
        )
        self.window = MainWindow(
            self.settings, self.library, self.sc, self.playlists, self.player
        )
        self.tray = Tray(app.windowIcon())

        self._wire()

    def _wire(self) -> None:
        self.window.activate_clip.connect(self.activate_clip)
        self.window.deactivate_clip.connect(self.deactivate_clip)
        self.window.volume_changed.connect(self._on_volume_changed)
        self.window.pause_options_changed.connect(self._on_pause_options_changed)
        self.window.set_track_wallpaper.connect(self.activate_track_wallpaper)
        self.player.error.connect(self._on_player_error)

        self.monitor.paused_changed.connect(self._on_pause_changed)

        self.tray.show_window_requested.connect(self._show_window)
        self.tray.pause_requested.connect(lambda: self.engine.set_paused(True, by_user=True))
        self.tray.resume_requested.connect(lambda: self.engine.set_paused(False, by_user=True))
        self.tray.stop_requested.connect(self._stop_wallpaper)
        self.tray.quit_requested.connect(self._quit)

    # ---------- lifecycle ----------
    def start(self) -> None:
        self.window.show()
        self.tray.show()
        # Auto-resume last wallpaper if any.
        cid = self.settings.active_clip_id
        if cid:
            clip = self.library.get(cid)
            if clip and clip.exists():
                try:
                    self.engine.start(clip.file, volume=self.settings.volume)
                    self.window.set_active_clip(cid)
                    self.tray.set_running(True)
                    self.monitor.start()
                except Exception as e:  # noqa: BLE001
                    log.exception("Failed to auto-resume wallpaper")
                    self.window.show_status(f"Не удалось возобновить обои: {e}")

    # ---------- events ----------
    def activate_clip(self, clip_id: str) -> None:
        clip = self.library.get(clip_id)
        if clip is None or not clip.exists():
            QMessageBox.warning(self.window, "ytwall", "Файл клипа не найден.")
            return
        if not self.engine.supported:
            QMessageBox.information(
                self.window,
                "ytwall",
                "Видео-обои поддерживаются только на Windows. UI работает в режиме предпросмотра.",
            )
            return
        try:
            self.engine.start(clip.file, volume=self.settings.volume)
        except Exception as e:  # noqa: BLE001
            log.exception("Failed to start wallpaper")
            QMessageBox.critical(self.window, "ytwall", f"Не удалось запустить обои:\n{e}")
            return
        self.settings.active_clip_id = clip_id
        self.settings.save()
        self.window.set_active_clip(clip_id)
        self.tray.set_running(True)
        self.monitor.start()
        self.window.show_status(f"Обои: {clip.title}")
        self.tray.notify("ytwall", f"Обои запущены: {clip.title}")

    def deactivate_clip(self, _clip_id: str) -> None:
        self._stop_wallpaper()

    def activate_track_wallpaper(self, track) -> None:  # noqa: ANN001
        """Set a SoundCloud track's cover as the wallpaper while audio plays
        in the mini-player."""
        if track is None:
            return
        if not self.engine.supported:
            QMessageBox.information(
                self.window,
                "ytwall",
                "Видео-обои поддерживаются только на Windows.",
            )
            return
        # Make sure the track is actually playing in the mini-player.
        if self.player.current is None or self.player.current.id != track.id:
            self.player.play_track(track)
        # Download cover synchronously (small file, ~50-200 KB) and use it as wallpaper.
        from .artwork import download_blocking

        artwork_url = track.display_artwork or track.artwork_url
        cover_path = download_blocking(artwork_url) if artwork_url else None
        if cover_path is None:
            QMessageBox.warning(
                self.window, "ytwall", "Не удалось скачать обложку трека."
            )
            return
        try:
            self.engine.start(str(cover_path), volume=0)  # audio comes from MusicPlayer, not engine
        except Exception as e:  # noqa: BLE001
            log.exception("Failed to start cover wallpaper")
            QMessageBox.critical(self.window, "ytwall", f"Не удалось запустить обои:\n{e}")
            return
        self.settings.active_clip_id = None  # detach video clip if any
        self.settings.save()
        self.window.set_active_clip(None)
        self.tray.set_running(True)
        self.monitor.start()
        self.window.show_status(f"Обои: {track.title}")
        self.tray.notify("ytwall", f"Обои: {track.title}")

    def _on_player_error(self, msg: str) -> None:
        log.warning("MusicPlayer error: %s", msg)
        self.window.show_status(f"Плеер: {msg}")

    def _stop_wallpaper(self) -> None:
        self.engine.stop()
        self.monitor.stop()
        self.settings.active_clip_id = None
        self.settings.save()
        self.window.set_active_clip(None)
        self.tray.set_running(False)
        self.window.show_status("Обои сняты")

    def _on_volume_changed(self, value: int) -> None:
        self.engine.set_volume(value)

    def _on_pause_options_changed(self) -> None:
        self.monitor.pause_on_fullscreen = self.settings.pause_on_fullscreen
        self.monitor.pause_on_battery = self.settings.pause_on_battery
        self.monitor.pause_when_obscured = self.settings.pause_when_obscured

    def _on_pause_changed(self, paused: bool, reason: str) -> None:
        self.engine.set_paused(paused)
        if paused:
            self.window.show_status(f"Пауза обоев · {reason}")
        else:
            self.window.show_status("Обои воспроизводятся")

    def _show_window(self) -> None:
        self.window.showNormal()
        self.window.raise_()
        self.window.activateWindow()

    def _quit(self) -> None:
        self.engine.stop()
        self.monitor.stop()
        self.tray.hide()
        self.app.quit()


def run(argv: list[str]) -> int:
    _configure_logging()
    QGuiApplication.setApplicationDisplayName("ytwall")
    app = QApplication(argv)
    app.setApplicationName("ytwall")
    app.setOrganizationName("ytwall")
    app.setQuitOnLastWindowClosed(False)
    app.setStyleSheet(QSS)
    app.setWindowIcon(_build_app_icon())

    ctrl = Controller(app)
    ctrl.start()

    return app.exec()
