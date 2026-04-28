"""Detect when the wallpaper should pause to save resources.

We poll periodically (every 500ms) and emit a `should_pause` signal whenever
the desktop is *not* visible to the user — for example because a fullscreen
app is in front, the workstation is locked, the user is on battery, or the
foreground window covers the entire monitor where the wallpaper lives.
"""

from __future__ import annotations

import ctypes
import logging
import sys
from ctypes import wintypes

from PySide6.QtCore import QObject, QTimer, Signal

log = logging.getLogger(__name__)


# QUNS_* values for SHQueryUserNotificationState
QUNS_NOT_PRESENT = 1
QUNS_BUSY = 2
QUNS_RUNNING_D3D_FULL_SCREEN = 3
QUNS_PRESENTATION_MODE = 4
QUNS_ACCEPTS_NOTIFICATIONS = 5
QUNS_QUIET_TIME = 6
QUNS_APP = 7

# WTS session lock notification
WTS_SESSION_LOCK = 0x7
WTS_SESSION_UNLOCK = 0x8


if sys.platform == "win32":
    user32 = ctypes.windll.user32
    shell32 = ctypes.windll.shell32
    kernel32 = ctypes.windll.kernel32

    user32.GetForegroundWindow.restype = wintypes.HWND
    user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
    user32.GetWindowRect.restype = wintypes.BOOL
    user32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    user32.GetClassNameW.restype = ctypes.c_int
    user32.MonitorFromWindow.restype = wintypes.HMONITOR

    class MONITORINFO(ctypes.Structure):
        _fields_ = (
            ("cbSize", wintypes.DWORD),
            ("rcMonitor", wintypes.RECT),
            ("rcWork", wintypes.RECT),
            ("dwFlags", wintypes.DWORD),
        )

    user32.GetMonitorInfoW.argtypes = [wintypes.HMONITOR, ctypes.POINTER(MONITORINFO)]
    user32.GetMonitorInfoW.restype = wintypes.BOOL

    shell32.SHQueryUserNotificationState.argtypes = [ctypes.POINTER(ctypes.c_int)]
    shell32.SHQueryUserNotificationState.restype = ctypes.c_long


def _foreground_class() -> str:
    if sys.platform != "win32":
        return ""
    hwnd = user32.GetForegroundWindow()
    if not hwnd:
        return ""
    buf = ctypes.create_unicode_buffer(256)
    user32.GetClassNameW(hwnd, buf, 256)
    return buf.value


def _foreground_is_fullscreen() -> bool:
    if sys.platform != "win32":
        return False
    hwnd = user32.GetForegroundWindow()
    if not hwnd:
        return False
    cls = _foreground_class()
    # Desktop or shell windows shouldn't trigger pause.
    if cls in {"Progman", "WorkerW", "Shell_TrayWnd", ""}:
        return False
    rect = wintypes.RECT()
    if not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
        return False
    monitor = user32.MonitorFromWindow(hwnd, 2)  # MONITOR_DEFAULTTONEAREST
    if not monitor:
        return False
    mi = MONITORINFO()
    mi.cbSize = ctypes.sizeof(MONITORINFO)
    if not user32.GetMonitorInfoW(monitor, ctypes.byref(mi)):
        return False
    m = mi.rcMonitor
    return (
        rect.left <= m.left
        and rect.top <= m.top
        and rect.right >= m.right
        and rect.bottom >= m.bottom
    )


def _user_notification_state() -> int:
    if sys.platform != "win32":
        return QUNS_ACCEPTS_NOTIFICATIONS
    state = ctypes.c_int(0)
    hr = shell32.SHQueryUserNotificationState(ctypes.byref(state))
    if hr != 0:
        return QUNS_ACCEPTS_NOTIFICATIONS
    return int(state.value)


def _on_battery() -> bool:
    """Return True if the system is currently running on battery power."""
    if sys.platform != "win32":
        return False
    try:
        import psutil  # local import; psutil is in deps
    except ImportError:
        return False
    bat = psutil.sensors_battery()
    if bat is None:
        return False
    return not bat.power_plugged


class PauseReason:
    NONE = ""
    FULLSCREEN = "Полноэкранное приложение"
    LOCKED = "Сеанс заблокирован"
    PRESENTATION = "Режим презентации"
    BATTERY = "Питание от батареи"
    BUSY = "Не беспокоить"


class PauseMonitor(QObject):
    """Polls the system and emits `paused_changed(bool, reason)`."""

    paused_changed = Signal(bool, str)

    def __init__(
        self,
        *,
        pause_on_fullscreen: bool = True,
        pause_on_battery: bool = True,
        pause_when_obscured: bool = True,
        interval_ms: int = 500,
    ) -> None:
        super().__init__()
        self.pause_on_fullscreen = pause_on_fullscreen
        self.pause_on_battery = pause_on_battery
        self.pause_when_obscured = pause_when_obscured
        self._timer = QTimer(self)
        self._timer.setInterval(interval_ms)
        self._timer.timeout.connect(self._tick)
        self._last: tuple[bool, str] = (False, "")

    def start(self) -> None:
        if sys.platform != "win32":
            return
        self._timer.start()

    def stop(self) -> None:
        self._timer.stop()
        if self._last[0]:
            self._last = (False, "")
            self.paused_changed.emit(False, "")

    def _tick(self) -> None:
        paused, reason = self._evaluate()
        if (paused, reason) != self._last:
            self._last = (paused, reason)
            self.paused_changed.emit(paused, reason)

    def _evaluate(self) -> tuple[bool, str]:
        state = _user_notification_state()
        if state in (QUNS_RUNNING_D3D_FULL_SCREEN, QUNS_PRESENTATION_MODE):
            if self.pause_on_fullscreen:
                return True, PauseReason.PRESENTATION
        if state == QUNS_NOT_PRESENT:
            return True, PauseReason.LOCKED
        if state == QUNS_BUSY and self.pause_on_fullscreen:
            return True, PauseReason.BUSY

        if self.pause_when_obscured and _foreground_is_fullscreen():
            return True, PauseReason.FULLSCREEN

        if self.pause_on_battery and _on_battery():
            return True, PauseReason.BATTERY

        return False, PauseReason.NONE
