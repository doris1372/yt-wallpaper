from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
)

from ..library import Clip


def _format_duration(seconds: float) -> str:
    s = int(max(0.0, seconds))
    m, s = divmod(s, 60)
    h, m = divmod(m, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


class ClipCard(QFrame):
    activate_requested = Signal(str)  # clip_id
    deactivate_requested = Signal(str)
    delete_requested = Signal(str)
    open_folder_requested = Signal(str)

    def __init__(self, clip: Clip) -> None:
        super().__init__()
        self.setObjectName("clipCard")
        self.clip = clip
        self._active = False
        self._build_ui()

    def _build_ui(self) -> None:
        self.setFixedHeight(150)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(16)

        # thumbnail
        self.thumb = QLabel()
        self.thumb.setObjectName("thumb")
        self.thumb.setFixedSize(220, 124)
        self.thumb.setAlignment(Qt.AlignCenter)
        if self.clip.thumbnail and Path(self.clip.thumbnail).exists():
            pix = QPixmap(self.clip.thumbnail).scaled(
                220, 124, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation
            )
            self.thumb.setPixmap(pix)
        else:
            self.thumb.setText("🎬")
            self.thumb.setStyleSheet("font-size: 36px; color: #4b5160;")
        layout.addWidget(self.thumb)

        # text + actions
        col = QVBoxLayout()
        col.setSpacing(6)

        header = QHBoxLayout()
        title = QLabel(self.clip.title)
        title.setObjectName("h2")
        title.setWordWrap(True)
        header.addWidget(title, 1)

        self.playing_badge = QLabel("ИГРАЕТ")
        self.playing_badge.setObjectName("playing")
        self.playing_badge.hide()
        header.addWidget(self.playing_badge, 0, Qt.AlignTop)
        col.addLayout(header)

        meta_parts: list[str] = []
        if self.clip.artist:
            meta_parts.append(self.clip.artist)
        if self.clip.duration:
            meta_parts.append(_format_duration(self.clip.duration))
        if self.clip.width and self.clip.height:
            meta_parts.append(f"{self.clip.width}×{self.clip.height}")
        meta = QLabel(" · ".join(meta_parts) or " ")
        meta.setObjectName("muted")
        col.addWidget(meta)

        col.addStretch(1)

        actions = QHBoxLayout()
        actions.setSpacing(8)

        self.toggle_btn = QPushButton("Поставить на обои")
        self.toggle_btn.setObjectName("primary")
        self.toggle_btn.clicked.connect(self._on_toggle)
        actions.addWidget(self.toggle_btn)

        folder_btn = QPushButton("В папке")
        folder_btn.setObjectName("ghost")
        folder_btn.clicked.connect(lambda: self.open_folder_requested.emit(self.clip.id))
        actions.addWidget(folder_btn)

        del_btn = QPushButton("Удалить")
        del_btn.setObjectName("ghost")
        del_btn.clicked.connect(lambda: self.delete_requested.emit(self.clip.id))
        actions.addWidget(del_btn)

        actions.addStretch(1)
        col.addLayout(actions)

        layout.addLayout(col, 1)

    def set_active(self, active: bool) -> None:
        self._active = active
        self.setProperty("active", "true" if active else "false")
        self.style().unpolish(self)
        self.style().polish(self)
        self.playing_badge.setVisible(active)
        self.toggle_btn.setText("Снять с обоев" if active else "Поставить на обои")
        self.toggle_btn.setObjectName("danger" if active else "primary")
        self.toggle_btn.style().unpolish(self.toggle_btn)
        self.toggle_btn.style().polish(self.toggle_btn)

    def _on_toggle(self) -> None:
        if self._active:
            self.deactivate_requested.emit(self.clip.id)
        else:
            self.activate_requested.emit(self.clip.id)
