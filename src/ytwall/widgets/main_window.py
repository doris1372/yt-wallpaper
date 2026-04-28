from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QStackedWidget,
    QStatusBar,
    QVBoxLayout,
    QWidget,
)

from ..config import Settings
from ..library import Library
from ..music_player import MusicPlayer
from ..playlists import Playlists
from ..soundcloud import SoundCloudClient
from .download_tab import DownloadTab
from .library_tab import LibraryTab
from .mini_player import MiniPlayer
from .music_tab import MusicTab
from .settings_tab import SettingsTab


class _NavButton(QPushButton):
    def __init__(self, text: str, icon_text: str = "") -> None:
        super().__init__(f"  {icon_text}   {text}")
        self.setObjectName("nav")
        self.setProperty("active", "false")
        self.setCursor(Qt.PointingHandCursor)
        self.setCheckable(True)

    def set_active(self, active: bool) -> None:
        self.setProperty("active", "true" if active else "false")
        self.setChecked(active)
        self.style().unpolish(self)
        self.style().polish(self)


class MainWindow(QMainWindow):
    activate_clip = Signal(str)
    deactivate_clip = Signal(str)
    volume_changed = Signal(int)
    pause_options_changed = Signal()
    settings_changed = Signal()
    set_track_wallpaper = Signal(object)  # SoundCloud Track

    def __init__(
        self,
        settings: Settings,
        library: Library,
        sc_client: SoundCloudClient,
        playlists: Playlists,
        player: MusicPlayer,
    ) -> None:
        super().__init__()
        self.settings = settings
        self.library = library
        self.sc = sc_client
        self.playlists = playlists
        self.player = player

        self.setWindowTitle("ytwall — Music & Live Wallpapers")
        self.setMinimumSize(1000, 660)
        self.resize(1180, 760)

        root = QWidget()
        root.setObjectName("root")
        self.setCentralWidget(root)
        outer = QVBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # body row: sidebar + stack
        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)

        # ---------- Sidebar ----------
        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        side_l = QVBoxLayout(sidebar)
        side_l.setContentsMargins(0, 0, 0, 12)
        side_l.setSpacing(0)

        brand = QLabel("ytwall")
        brand.setObjectName("brand")
        sub = QLabel("MUSIC + LIVE WALLPAPERS")
        sub.setObjectName("brand-sub")
        side_l.addWidget(brand)
        side_l.addWidget(sub)

        self.btn_music = _NavButton("Музыка", "♪")
        self.btn_clips = _NavButton("Клипы", "▶")
        self.btn_download = _NavButton("Загрузка", "↓")
        self.btn_settings = _NavButton("Настройки", "⚙")

        for b in (self.btn_music, self.btn_clips, self.btn_download, self.btn_settings):
            side_l.addWidget(b)

        side_l.addStretch(1)

        body.addWidget(sidebar)

        # ---------- Stacked content ----------
        self.stack = QStackedWidget()
        body.addWidget(self.stack, 1)

        self.music_tab = MusicTab(self.sc, self.player, self.playlists)
        self.clips_tab = LibraryTab(library)
        self.download_tab = DownloadTab(settings, library)
        self.settings_tab = SettingsTab(settings)
        self.stack.addWidget(self.music_tab)     # 0
        self.stack.addWidget(self.clips_tab)     # 1
        self.stack.addWidget(self.download_tab)  # 2
        self.stack.addWidget(self.settings_tab)  # 3

        self.btn_music.clicked.connect(lambda: self._switch(0))
        self.btn_clips.clicked.connect(lambda: self._switch(1))
        self.btn_download.clicked.connect(lambda: self._switch(2))
        self.btn_settings.clicked.connect(lambda: self._switch(3))

        outer.addLayout(body, 1)

        # ---------- Mini-player strip ----------
        self.mini_player = MiniPlayer(self.player)
        outer.addWidget(self.mini_player)

        # ---------- Plumbing ----------
        self.download_tab.clip_added.connect(self._on_clip_added)
        self.clips_tab.activate_requested.connect(self.activate_clip.emit)
        self.clips_tab.deactivate_requested.connect(self.deactivate_clip.emit)
        self.settings_tab.volume_changed.connect(self.volume_changed.emit)
        self.settings_tab.pause_options_changed.connect(self.pause_options_changed.emit)
        self.settings_tab.settings_changed.connect(self.settings_changed.emit)
        self.music_tab.set_wallpaper_request.connect(self.set_track_wallpaper.emit)
        self.mini_player.set_wallpaper_clicked.connect(self._on_mini_wallpaper)

        self._switch(0)
        self.setStatusBar(QStatusBar())
        self.statusBar().showMessage("Готов")

    # ---------- public API ----------
    def show_status(self, message: str, *, kind: str = "info") -> None:
        self.statusBar().showMessage(message)

    def set_active_clip(self, clip_id: str | None) -> None:
        self.clips_tab.set_active_clip(clip_id)

    # ---------- internal ----------
    def _switch(self, index: int) -> None:
        self.stack.setCurrentIndex(index)
        self.btn_music.set_active(index == 0)
        self.btn_clips.set_active(index == 1)
        self.btn_download.set_active(index == 2)
        self.btn_settings.set_active(index == 3)
        if index == 1:
            self.clips_tab.refresh()

    def _on_clip_added(self, clip) -> None:  # noqa: ANN001
        self.clips_tab.refresh()
        self._switch(1)
        self.show_status(f"«{clip.title}» добавлен в библиотеку клипов")
        _ = QIcon

    def _on_mini_wallpaper(self, track) -> None:  # noqa: ANN001
        if track is not None:
            self.set_track_wallpaper.emit(track)
