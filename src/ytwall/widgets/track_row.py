"""Single track row used inside the Music tab and inside playlists."""
from __future__ import annotations

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QMenu,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ..artwork import ArtworkLoader
from ..soundcloud import Track


class TrackRow(QFrame):
    play_clicked = Signal(object)  # Track
    add_to_playlist_clicked = Signal(object)  # Track
    set_wallpaper_clicked = Signal(object)  # Track

    COVER_SIZE = QSize(56, 56)

    def __init__(self, track: Track) -> None:
        super().__init__()
        self.track = track
        self.setObjectName("trackRow")
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setFixedHeight(72)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(14)

        self.cover_label = QLabel()
        self.cover_label.setFixedSize(self.COVER_SIZE)
        self.cover_label.setObjectName("trackCover")
        self.cover_label.setStyleSheet(
            "QLabel#trackCover { border-radius: 6px; background: #1d1f24; }"
        )
        self.cover_label.setScaledContents(False)
        self.cover_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.cover_label)

        text_col = QVBoxLayout()
        text_col.setSpacing(2)
        self.title_label = QLabel(track.title)
        self.title_label.setObjectName("trackTitle")
        self.title_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.artist_label = QLabel(track.artist)
        self.artist_label.setObjectName("muted")
        text_col.addWidget(self.title_label)
        text_col.addWidget(self.artist_label)
        layout.addLayout(text_col, 1)

        self.duration_label = QLabel(track.duration_str)
        self.duration_label.setObjectName("muted")
        layout.addWidget(self.duration_label)

        self.play_button = QPushButton("▶")
        self.play_button.setObjectName("primary")
        self.play_button.setFixedSize(40, 40)
        self.play_button.setToolTip("Слушать")
        self.play_button.clicked.connect(lambda: self.play_clicked.emit(self.track))
        layout.addWidget(self.play_button)

        self.menu_button = QPushButton("•••")
        self.menu_button.setObjectName("ghost")
        self.menu_button.setFixedSize(48, 40)
        self.menu_button.setToolTip("Действия")
        self.menu_button.clicked.connect(self._show_menu)
        layout.addWidget(self.menu_button)

        self._load_cover()

    # ---------- cover ----------
    def _load_cover(self) -> None:
        loader = ArtworkLoader.instance()
        url = self.track.display_artwork or self.track.artwork_url
        pm = loader.request(url, self.COVER_SIZE)
        if pm is not None:
            self._apply_cover(pm)
            return
        # Listen once for ready signal.
        if url:
            loader.ready.connect(self._on_ready)
            self._waiting_url = url
        # Placeholder: first letter of title in a colored box (handled by stylesheet)
        self.cover_label.setText("♪")
        self.cover_label.setStyleSheet(
            self.cover_label.styleSheet() + " color:#7a7d86; font-size:18px;"
        )

    def _on_ready(self, url: str, pm: QPixmap) -> None:
        if getattr(self, "_waiting_url", None) != url:
            return
        try:
            ArtworkLoader.instance().ready.disconnect(self._on_ready)
        except (TypeError, RuntimeError):
            pass
        self._apply_cover(pm)

    def _apply_cover(self, pm: QPixmap) -> None:
        # Crop center to cover size
        cropped = pm.copy(
            (pm.width() - self.COVER_SIZE.width()) // 2,
            (pm.height() - self.COVER_SIZE.height()) // 2,
            self.COVER_SIZE.width(),
            self.COVER_SIZE.height(),
        )
        self.cover_label.setPixmap(cropped)
        self.cover_label.setText("")

    # ---------- menu ----------
    def _show_menu(self) -> None:
        menu = QMenu(self)
        menu.addAction("Добавить в плейлист…", lambda: self.add_to_playlist_clicked.emit(self.track))
        menu.addAction("На обои (обложка + аудио)", lambda: self.set_wallpaper_clicked.emit(self.track))
        menu.exec(self.menu_button.mapToGlobal(self.menu_button.rect().bottomLeft()))


class TrackList(QWidget):
    """Scrollable container of TrackRow widgets — re-emits row signals."""

    play_clicked = Signal(object)
    add_to_playlist_clicked = Signal(object)
    set_wallpaper_clicked = Signal(object)

    def __init__(self) -> None:
        super().__init__()
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(2)
        self._layout.addStretch(1)

    def clear(self) -> None:
        # Remove all existing TrackRow widgets except the trailing stretch.
        while self._layout.count() > 1:
            item = self._layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()

    def set_tracks(self, tracks: list[Track]) -> None:
        self.clear()
        for track in tracks:
            row = TrackRow(track)
            row.play_clicked.connect(self.play_clicked)
            row.add_to_playlist_clicked.connect(self.add_to_playlist_clicked)
            row.set_wallpaper_clicked.connect(self.set_wallpaper_clicked)
            self._layout.insertWidget(self._layout.count() - 1, row)
