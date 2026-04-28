"""Mini-player strip shown at the bottom of the main window."""
from __future__ import annotations

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSlider,
    QVBoxLayout,
)

from ..artwork import ArtworkLoader
from ..music_player import MusicPlayer
from ..soundcloud import Track


def _fmt_seconds(s: float) -> str:
    s = int(max(0.0, s))
    h, rem = divmod(s, 3600)
    m, sec = divmod(rem, 60)
    if h:
        return f"{h}:{m:02d}:{sec:02d}"
    return f"{m}:{sec:02d}"


class MiniPlayer(QFrame):
    set_wallpaper_clicked = Signal(object)  # current Track or None

    COVER_SIZE = QSize(48, 48)

    def __init__(self, player: MusicPlayer) -> None:
        super().__init__()
        self.player = player
        self._current: Track | None = None
        self.setObjectName("miniPlayer")
        self.setFixedHeight(72)
        self._build_ui()
        self._wire()
        self._refresh_track(None)

    def _build_ui(self) -> None:
        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 8, 16, 8)
        layout.setSpacing(14)

        self.cover = QLabel()
        self.cover.setFixedSize(self.COVER_SIZE)
        self.cover.setObjectName("miniCover")
        self.cover.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.cover.setStyleSheet(
            "QLabel#miniCover { border-radius: 6px; background:#15171b; color:#666; font-size: 18px; }"
        )
        self.cover.setText("♪")
        layout.addWidget(self.cover)

        text_col = QVBoxLayout()
        text_col.setSpacing(2)
        self.title_label = QLabel("Ничего не играет")
        self.title_label.setObjectName("miniTitle")
        self.artist_label = QLabel("")
        self.artist_label.setObjectName("muted")
        text_col.addWidget(self.title_label)
        text_col.addWidget(self.artist_label)
        layout.addLayout(text_col, 0)

        # transport buttons
        self.prev_btn = QPushButton("◀◀")
        self.prev_btn.setObjectName("ghost")
        self.prev_btn.setFixedSize(36, 36)
        self.prev_btn.clicked.connect(self.player.prev)
        layout.addWidget(self.prev_btn)

        self.play_btn = QPushButton("▶")
        self.play_btn.setObjectName("primary")
        self.play_btn.setFixedSize(40, 40)
        self.play_btn.clicked.connect(self.player.play_pause)
        layout.addWidget(self.play_btn)

        self.next_btn = QPushButton("▶▶")
        self.next_btn.setObjectName("ghost")
        self.next_btn.setFixedSize(36, 36)
        self.next_btn.clicked.connect(self.player.next)
        layout.addWidget(self.next_btn)

        # progress
        progress_col = QVBoxLayout()
        progress_col.setSpacing(2)
        self.progress = QSlider(Qt.Horizontal)
        self.progress.setRange(0, 1000)
        self.progress.setEnabled(False)
        progress_col.addWidget(self.progress)

        time_row = QHBoxLayout()
        self.cur_label = QLabel("0:00")
        self.cur_label.setObjectName("muted")
        self.tot_label = QLabel("0:00")
        self.tot_label.setObjectName("muted")
        time_row.addWidget(self.cur_label)
        time_row.addStretch(1)
        time_row.addWidget(self.tot_label)
        progress_col.addLayout(time_row)
        layout.addLayout(progress_col, 1)

        # volume
        self.volume = QSlider(Qt.Horizontal)
        self.volume.setRange(0, 100)
        self.volume.setValue(self.player.volume)
        self.volume.setFixedWidth(120)
        self.volume.valueChanged.connect(self.player.set_volume)
        layout.addWidget(QLabel("Vol"))
        layout.addWidget(self.volume)

        # set wallpaper button
        self.wp_btn = QPushButton("На обои")
        self.wp_btn.setObjectName("ghost")
        self.wp_btn.setToolTip("Поставить обложку текущего трека на рабочий стол")
        self.wp_btn.clicked.connect(lambda: self.set_wallpaper_clicked.emit(self._current))
        self.wp_btn.setEnabled(False)
        layout.addWidget(self.wp_btn)

    def _wire(self) -> None:
        self.player.track_changed.connect(self._refresh_track)
        self.player.play_state_changed.connect(self._refresh_play_state)
        self.player.position_changed.connect(self._refresh_position)

    # ---------- slots ----------
    def _refresh_track(self, track: Track | None) -> None:
        self._current = track
        if track is None:
            self.title_label.setText("Ничего не играет")
            self.artist_label.setText("")
            self.cover.setPixmap(QPixmap())
            self.cover.setText("♪")
            self.play_btn.setText("▶")
            self.progress.setValue(0)
            self.progress.setEnabled(False)
            self.cur_label.setText("0:00")
            self.tot_label.setText("0:00")
            self.wp_btn.setEnabled(False)
            return
        self.title_label.setText(track.title)
        self.artist_label.setText(track.artist)
        self.progress.setEnabled(True)
        self.wp_btn.setEnabled(True)
        # Cover
        url = track.display_artwork or track.artwork_url
        loader = ArtworkLoader.instance()
        pm = loader.request(url, self.COVER_SIZE)
        if pm is not None:
            self._set_cover_pixmap(pm)
        else:
            self.cover.setPixmap(QPixmap())
            self.cover.setText("♪")
            try:
                loader.ready.disconnect(self._on_art_ready)
            except (TypeError, RuntimeError):
                pass
            loader.ready.connect(self._on_art_ready)
            self._art_url = url

    def _on_art_ready(self, url: str, pm: QPixmap) -> None:
        if getattr(self, "_art_url", None) != url:
            return
        self._set_cover_pixmap(pm)

    def _set_cover_pixmap(self, pm: QPixmap) -> None:
        cropped = pm.copy(
            (pm.width() - self.COVER_SIZE.width()) // 2,
            (pm.height() - self.COVER_SIZE.height()) // 2,
            self.COVER_SIZE.width(),
            self.COVER_SIZE.height(),
        )
        self.cover.setPixmap(cropped)
        self.cover.setText("")

    def _refresh_play_state(self, playing: bool) -> None:
        self.play_btn.setText("⏸" if playing else "▶")

    def _refresh_position(self, pos: float, dur: float) -> None:
        if dur <= 0:
            return
        ratio = max(0, min(1000, int(pos / dur * 1000)))
        if not self.progress.isSliderDown():
            self.progress.setValue(ratio)
        self.cur_label.setText(_fmt_seconds(pos))
        self.tot_label.setText(_fmt_seconds(dur))
