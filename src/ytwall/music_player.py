"""Audio-only music player wrapping libmpv.

Singleton ``MusicPlayer`` exposes Qt signals so widgets across the UI can
observe play state, current track, position, and queue without holding
direct references to mpv objects.

Threading model:
- libmpv runs its own background threads.
- All Qt signals are emitted via ``QMetaObject.invokeMethod`` (queued)
  from a ``QTimer`` polling mpv state on the main thread, so listeners
  always run on the GUI thread.
"""
from __future__ import annotations

import logging
import os
import threading

from PySide6.QtCore import QObject, QTimer, Signal

from .soundcloud import SoundCloudClient, SoundCloudError, Track

log = logging.getLogger(__name__)


class MusicPlayer(QObject):
    track_changed = Signal(object)  # Track or None
    play_state_changed = Signal(bool)  # True if playing
    position_changed = Signal(float, float)  # pos_seconds, duration_seconds
    queue_changed = Signal()
    error = Signal(str)

    _instance: MusicPlayer | None = None

    def __init__(self, sc_client: SoundCloudClient, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._sc = sc_client
        self._mpv = None  # lazy-init to keep startup quick
        self._mpv_lock = threading.Lock()
        self._queue: list[Track] = []
        self._index: int = -1
        self._current: Track | None = None
        self._wave_seed: Track | None = None
        self._is_playing = False
        self._volume = 80

        # Poll mpv state from the GUI thread.
        self._poll = QTimer(self)
        self._poll.setInterval(250)
        self._poll.timeout.connect(self._poll_state)
        self._poll.start()

        MusicPlayer._instance = self

    # ------------- mpv plumbing -------------
    def _ensure_mpv(self):
        if self._mpv is not None:
            return self._mpv
        with self._mpv_lock:
            if self._mpv is None:
                import mpv

                kwargs = {
                    "vid": "no",
                    "audio_display": "no",
                    "keep_open": "no",
                    "cache": "yes",
                    "demuxer_max_bytes": 64 * 1024 * 1024,
                }
                # Optional override for headless / no-audio environments.
                ao_override = os.environ.get("YTWALL_MPV_AO")
                if ao_override:
                    kwargs["ao"] = ao_override
                self._mpv = mpv.MPV(**kwargs)
                # Auto-advance when track ends.
                @self._mpv.event_callback("end-file")
                def _on_end_file(event):
                    # python-mpv ≥1.0 hands us an MpvEvent object whose
                    # underlying end-file struct lives at .data.reason.
                    # Older paths used a dict-shaped event. Be tolerant.
                    try:
                        reason = None
                        data = getattr(event, "data", None)
                        if data is None and hasattr(event, "get"):
                            data = event.get("event") or {}
                        if hasattr(data, "reason"):
                            reason = data.reason
                        elif isinstance(data, dict):
                            reason = data.get("reason")
                        # libmpv reason: 0 == EOF (also "eof" in some bindings).
                        if reason in (0, "eof"):
                            QTimer.singleShot(0, self.next)
                    except Exception:  # noqa: BLE001
                        log.exception("end-file handler failed")

                self._mpv.volume = self._volume
        return self._mpv

    def shutdown(self) -> None:
        try:
            self._poll.stop()
        except Exception:  # noqa: BLE001
            pass
        if self._mpv is not None:
            try:
                self._mpv.stop()
                self._mpv.terminate()
            except Exception:  # noqa: BLE001
                pass
        self._mpv = None

    # ------------- public API -------------
    @property
    def current(self) -> Track | None:
        return self._current

    @property
    def queue(self) -> list[Track]:
        return list(self._queue)

    @property
    def is_playing(self) -> bool:
        return self._is_playing

    @property
    def volume(self) -> int:
        return self._volume

    def set_volume(self, value: int) -> None:
        value = max(0, min(100, int(value)))
        self._volume = value
        if self._mpv is not None:
            try:
                self._mpv.volume = value
            except Exception:  # noqa: BLE001
                pass

    def set_queue(self, tracks: list[Track], start_index: int = 0, wave_seed: Track | None = None) -> None:
        self._queue = list(tracks)
        self._wave_seed = wave_seed
        if not tracks:
            self._index = -1
            self._stop_internal()
            self.queue_changed.emit()
            return
        self._index = max(0, min(start_index, len(tracks) - 1))
        self.queue_changed.emit()
        self._play_current()

    def play_track(self, track: Track) -> None:
        """Replace queue with a single track and play it."""
        self.set_queue([track], 0)

    def play_pause(self) -> None:
        if self._mpv is None or self._current is None:
            return
        try:
            self._mpv.pause = not bool(self._mpv.pause)
        except Exception as e:  # noqa: BLE001
            self.error.emit(str(e))

    def stop(self) -> None:
        self._stop_internal()

    def next(self) -> None:
        if not self._queue:
            return
        if self._index + 1 < len(self._queue):
            self._index += 1
            self._play_current()
            return
        # End of queue. In wave mode, fetch related and continue.
        if self._wave_seed is not None or self._current is not None:
            seed = self._wave_seed or self._current
            try:
                more = self._sc.related(seed.id, limit=20) if seed else []
            except SoundCloudError as e:
                self.error.emit(f"Не удалось получить рекомендации: {e}")
                more = []
            # Drop already-played to avoid loops.
            played_ids = {t.id for t in self._queue}
            fresh = [t for t in more if t.id not in played_ids]
            if fresh:
                self._queue.extend(fresh)
                self._index += 1
                self.queue_changed.emit()
                self._play_current()
                return
        # Otherwise: stop at end.
        self._stop_internal()

    def prev(self) -> None:
        if not self._queue:
            return
        if self._index - 1 >= 0:
            self._index -= 1
            self._play_current()

    # ------------- internal -------------
    def _play_current(self) -> None:
        if self._index < 0 or self._index >= len(self._queue):
            self._stop_internal()
            return
        track = self._queue[self._index]
        self._current = track
        self.track_changed.emit(track)
        try:
            url = self._sc.stream_url(track)
        except SoundCloudError as e:
            self.error.emit(f"Не удалось получить ссылку на трек: {e}")
            QTimer.singleShot(0, self.next)
            return
        try:
            mpv = self._ensure_mpv()
            mpv.pause = False
            mpv.play(url)
        except Exception as e:  # noqa: BLE001
            self.error.emit(f"mpv: {e}")
            return

    def _stop_internal(self) -> None:
        self._current = None
        self._is_playing = False
        if self._mpv is not None:
            try:
                self._mpv.stop()
            except Exception:  # noqa: BLE001
                pass
        self.track_changed.emit(None)
        self.play_state_changed.emit(False)
        self.position_changed.emit(0.0, 0.0)

    def _poll_state(self) -> None:
        if self._mpv is None or self._current is None:
            if self._is_playing:
                self._is_playing = False
                self.play_state_changed.emit(False)
            return
        try:
            paused = bool(self._mpv.pause)
            pos = float(self._mpv.time_pos or 0.0)
            dur = float(self._mpv.duration or (self._current.duration_ms / 1000.0))
        except Exception:  # noqa: BLE001
            return
        playing = not paused
        if playing != self._is_playing:
            self._is_playing = playing
            self.play_state_changed.emit(playing)
        self.position_changed.emit(pos, dur)
