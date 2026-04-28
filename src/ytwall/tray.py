from __future__ import annotations

from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QAction, QIcon, QPixmap
from PySide6.QtWidgets import QMenu, QSystemTrayIcon


def _fallback_icon() -> QIcon:
    pix = QPixmap(64, 64)
    pix.fill()
    return QIcon(pix)


class Tray(QObject):
    show_window_requested = Signal()
    pause_requested = Signal()
    resume_requested = Signal()
    stop_requested = Signal()
    quit_requested = Signal()

    def __init__(self, icon: QIcon | None = None) -> None:
        super().__init__()
        self._tray = QSystemTrayIcon(icon or _fallback_icon())
        self._tray.setToolTip("ytwall — видео-обои")
        menu = QMenu()

        self.act_open = QAction("Открыть ytwall", menu)
        self.act_open.triggered.connect(self.show_window_requested.emit)
        menu.addAction(self.act_open)

        menu.addSeparator()

        self.act_pause = QAction("Пауза обоев", menu)
        self.act_pause.triggered.connect(self.pause_requested.emit)
        menu.addAction(self.act_pause)

        self.act_resume = QAction("Возобновить обои", menu)
        self.act_resume.triggered.connect(self.resume_requested.emit)
        menu.addAction(self.act_resume)

        self.act_stop = QAction("Снять обои", menu)
        self.act_stop.triggered.connect(self.stop_requested.emit)
        menu.addAction(self.act_stop)

        menu.addSeparator()

        self.act_quit = QAction("Выход", menu)
        self.act_quit.triggered.connect(self.quit_requested.emit)
        menu.addAction(self.act_quit)

        self._tray.setContextMenu(menu)
        self._tray.activated.connect(self._on_activated)

    def show(self) -> None:
        self._tray.show()

    def hide(self) -> None:
        self._tray.hide()

    def set_running(self, running: bool) -> None:
        self.act_pause.setEnabled(running)
        self.act_resume.setEnabled(running)
        self.act_stop.setEnabled(running)

    def notify(self, title: str, message: str) -> None:
        self._tray.showMessage(title, message, QSystemTrayIcon.Information, 3000)

    def _on_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason == QSystemTrayIcon.Trigger:
            self.show_window_requested.emit()
