"""Video wallpaper engine for Windows.

Uses the classic Progman/WorkerW reparenting technique: we ask Progman to spawn
a WorkerW behind the desktop icons, then re-parent our borderless Qt window into
that WorkerW. mpv (libmpv) renders the video directly into our window.

This module is import-safe on non-Windows platforms (the Windows-specific calls
are guarded behind sys.platform checks). The wallpaper itself only works on
Windows; on other platforms the engine is a no-op stub useful for development.
"""

from __future__ import annotations

import ctypes
import logging
import sys
from ctypes import wintypes
from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QWidget

log = logging.getLogger(__name__)


def is_supported() -> bool:
    return sys.platform == "win32"


# ---------------------------------------------------------------------------
# Windows API helpers
# ---------------------------------------------------------------------------

if sys.platform == "win32":
    user32 = ctypes.windll.user32
    user32.FindWindowW.restype = wintypes.HWND
    user32.FindWindowExW.restype = wintypes.HWND
    user32.GetWindowLongW.restype = ctypes.c_long
    user32.SetWindowLongW.restype = ctypes.c_long
    user32.SetParent.restype = wintypes.HWND
    user32.SendMessageTimeoutW.restype = ctypes.c_long
    user32.SystemParametersInfoW.restype = wintypes.BOOL

    SMTO_NORMAL = 0x0000
    GWL_EXSTYLE = -20
    WS_EX_TOOLWINDOW = 0x00000080
    WS_EX_NOACTIVATE = 0x08000000

    SPIF_SENDCHANGE = 0x02
    SPI_SETDESKWALLPAPER = 0x0014


def _spawn_workerw() -> int | None:
    """Trigger Progman to create a WorkerW window behind desktop icons.

    Returns the HWND of the new WorkerW, or None on failure.
    """
    if sys.platform != "win32":
        return None

    progman = user32.FindWindowW("Progman", None)
    if not progman:
        log.error("Progman window not found")
        return None

    result = wintypes.LPARAM()
    user32.SendMessageTimeoutW(
        progman,
        0x052C,
        wintypes.WPARAM(0x0000000D),
        wintypes.LPARAM(0x00000001),
        SMTO_NORMAL,
        1000,
        ctypes.byref(result),
    )

    workerw_hwnd: int | None = None

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def enum_proc(hwnd, _):
        nonlocal workerw_hwnd
        # The desired WorkerW is the one that has SHELLDLL_DefView as child.
        shell_view = user32.FindWindowExW(hwnd, None, "SHELLDLL_DefView", None)
        if shell_view:
            sibling = user32.FindWindowExW(None, hwnd, "WorkerW", None)
            if sibling:
                workerw_hwnd = sibling
                return False
        return True

    user32.EnumWindows(enum_proc, 0)
    if workerw_hwnd:
        log.info("Found WorkerW HWND=0x%08X", workerw_hwnd)
    else:
        log.warning("WorkerW not found after Progman 0x052C")
    return workerw_hwnd


def _set_solid_wallpaper_color() -> None:
    """Reset the static wallpaper to a plain black image so transitions are clean.

    Uses an empty path which Windows treats as "no image"; combined with the
    desktop background colour, this prevents flashes of the previous wallpaper.
    """
    if sys.platform != "win32":
        return
    try:
        user32.SystemParametersInfoW(SPI_SETDESKWALLPAPER, 0, "", SPIF_SENDCHANGE)
    except OSError:
        pass


# ---------------------------------------------------------------------------
# Wallpaper window
# ---------------------------------------------------------------------------


class WallpaperWindow(QWidget):
    """Borderless full-virtual-screen window that hosts the mpv video output."""

    def __init__(self) -> None:
        super().__init__(None)
        self.setAttribute(Qt.WA_NativeWindow, True)
        self.setAttribute(Qt.WA_DontCreateNativeAncestors, True)
        self.setAttribute(Qt.WA_OpaquePaintEvent, True)
        self.setWindowFlag(Qt.FramelessWindowHint, True)
        self.setWindowFlag(Qt.Tool, True)
        self.setWindowTitle("ytwall-wallpaper")
        self.setStyleSheet("background-color: black;")
        self.setCursor(Qt.BlankCursor)

    def cover_virtual_screen(self) -> None:
        screens = QGuiApplication.screens()
        if not screens:
            return
        rect = screens[0].virtualGeometry()
        self.setGeometry(rect)


class WallpaperEngine:
    """Owns the wallpaper window and the mpv player. Single-instance."""

    def __init__(self) -> None:
        self._window: WallpaperWindow | None = None
        self._player = None  # mpv.MPV
        self._workerw: int | None = None
        self._current: str | None = None
        self._volume: int = 0
        self._paused_external: bool = False  # paused by optimization
        self._paused_user: bool = False  # paused by user

    # ---------- public API ----------
    @property
    def supported(self) -> bool:
        return is_supported()

    @property
    def is_running(self) -> bool:
        return self._window is not None and self._player is not None

    @property
    def current_file(self) -> str | None:
        return self._current

    def start(self, video_path: str, *, volume: int = 0) -> None:
        path = Path(video_path)
        if not path.exists():
            raise FileNotFoundError(video_path)

        self._volume = max(0, min(100, int(volume)))

        if self._window is None:
            self._window = WallpaperWindow()
            self._window.cover_virtual_screen()
            self._window.show()
            QTimer.singleShot(0, self._reparent_into_workerw)
            self._init_player()

        assert self._player is not None
        self._player.loop_file = "inf"
        self._player.volume = self._volume
        self._player.mute = self._volume == 0
        self._player.play(str(path))
        self._current = str(path)
        self._paused_user = False
        self._paused_external = False
        self._apply_pause_state()

    def stop(self) -> None:
        if self._player is not None:
            try:
                self._player.terminate()
            except Exception:  # noqa: BLE001
                pass
            self._player = None
        if self._window is not None:
            self._window.hide()
            self._window.deleteLater()
            self._window = None
        self._workerw = None
        self._current = None
        # Trigger desktop refresh so the static wallpaper comes back.
        if sys.platform == "win32":
            user32.InvalidateRect(None, None, True)

    def set_volume(self, volume: int) -> None:
        self._volume = max(0, min(100, int(volume)))
        if self._player is not None:
            self._player.volume = self._volume
            self._player.mute = self._volume == 0

    def set_paused(self, paused: bool, *, by_user: bool = False) -> None:
        if by_user:
            self._paused_user = paused
        else:
            self._paused_external = paused
        self._apply_pause_state()

    def _apply_pause_state(self) -> None:
        if self._player is None:
            return
        try:
            self._player.pause = bool(self._paused_external or self._paused_user)
        except Exception:  # noqa: BLE001
            pass

    # ---------- internals ----------
    def _init_player(self) -> None:
        try:
            import mpv  # type: ignore
        except (ImportError, OSError) as e:
            raise RuntimeError(
                "Не удалось загрузить libmpv. Положите mpv-2.dll рядом с ytwall.exe "
                "или добавьте mpv в PATH."
            ) from e

        assert self._window is not None
        wid = int(self._window.winId())

        self._player = mpv.MPV(
            wid=wid,
            vo="gpu",
            hwdec="auto-safe",
            keep_open="yes",
            loop_file="inf",
            input_default_bindings=False,
            input_vo_keyboard=False,
            osc=False,
            border=False,
            cursor_autohide="no",
            video_unscaled="no",
            keepaspect="no",  # stretch to fit; matches typical wallpaper behaviour
            mute="yes",
            volume=self._volume,
            ytdl=False,
        )

    def _reparent_into_workerw(self) -> None:
        if sys.platform != "win32" or self._window is None:
            return
        hwnd = int(self._window.winId())

        # Make sure the window doesn't show in taskbar / Alt-Tab.
        ex = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
        user32.SetWindowLongW(
            hwnd, GWL_EXSTYLE, ex | WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE
        )

        workerw = _spawn_workerw()
        if not workerw:
            log.error("Could not obtain WorkerW; wallpaper will float on top")
            return
        self._workerw = workerw
        prev = user32.SetParent(hwnd, workerw)
        log.info("Reparented wallpaper window 0x%08X into WorkerW (prev=0x%08X)", hwnd, prev or 0)
        # Re-cover the virtual screen *after* reparenting.
        self._window.cover_virtual_screen()
