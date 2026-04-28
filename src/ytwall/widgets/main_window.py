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
from .download_tab import DownloadTab
from .library_tab import LibraryTab
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

    def __init__(self, settings: Settings, library: Library) -> None:
        super().__init__()
        self.settings = settings
        self.library = library

        self.setWindowTitle("ytwall — Видео-обои с YouTube")
        self.setMinimumSize(960, 640)
        self.resize(1100, 720)

        root = QWidget()
        root.setObjectName("root")
        self.setCentralWidget(root)
        layout = QHBoxLayout(root)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # ---------- Sidebar ----------
        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        side_l = QVBoxLayout(sidebar)
        side_l.setContentsMargins(0, 0, 0, 12)
        side_l.setSpacing(0)

        brand = QLabel("ytwall")
        brand.setObjectName("brand")
        sub = QLabel("LIVE WALLPAPERS")
        sub.setObjectName("brand-sub")
        side_l.addWidget(brand)
        side_l.addWidget(sub)

        self.btn_download = _NavButton("Загрузка", "↓")
        self.btn_library = _NavButton("Музыка", "♪")
        self.btn_settings = _NavButton("Настройки", "⚙")

        for b in (self.btn_download, self.btn_library, self.btn_settings):
            side_l.addWidget(b)

        side_l.addStretch(1)

        layout.addWidget(sidebar)

        # ---------- Stacked content ----------
        self.stack = QStackedWidget()
        layout.addWidget(self.stack, 1)

        self.download_tab = DownloadTab(settings, library)
        self.library_tab = LibraryTab(library)
        self.settings_tab = SettingsTab(settings)
        self.stack.addWidget(self.download_tab)
        self.stack.addWidget(self.library_tab)
        self.stack.addWidget(self.settings_tab)

        self.btn_download.clicked.connect(lambda: self._switch(0))
        self.btn_library.clicked.connect(lambda: self._switch(1))
        self.btn_settings.clicked.connect(lambda: self._switch(2))

        # plumbing
        self.download_tab.clip_added.connect(self._on_clip_added)
        self.library_tab.activate_requested.connect(self.activate_clip.emit)
        self.library_tab.deactivate_requested.connect(self.deactivate_clip.emit)
        self.settings_tab.volume_changed.connect(self.volume_changed.emit)
        self.settings_tab.pause_options_changed.connect(self.pause_options_changed.emit)
        self.settings_tab.settings_changed.connect(self.settings_changed.emit)

        self._switch(0)
        self.setStatusBar(QStatusBar())
        self.statusBar().showMessage("Готов")

    # ---------- public API ----------
    def show_status(self, message: str, *, kind: str = "info") -> None:
        self.statusBar().showMessage(message)

    def set_active_clip(self, clip_id: str | None) -> None:
        self.library_tab.set_active_clip(clip_id)

    # ---------- internal ----------
    def _switch(self, index: int) -> None:
        self.stack.setCurrentIndex(index)
        self.btn_download.set_active(index == 0)
        self.btn_library.set_active(index == 1)
        self.btn_settings.set_active(index == 2)
        if index == 1:
            self.library_tab.refresh()

    def _on_clip_added(self, clip) -> None:  # noqa: ANN001
        self.library_tab.refresh()
        self._switch(1)
        self.show_status(f"«{clip.title}» добавлен в библиотеку")
        _ = QIcon  # keep import used in case we wire icons later
