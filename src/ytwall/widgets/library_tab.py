from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ..library import Library
from .clip_card import ClipCard


class LibraryTab(QWidget):
    activate_requested = Signal(str)  # clip_id
    deactivate_requested = Signal(str)

    def __init__(self, library: Library) -> None:
        super().__init__()
        self.library = library
        self._cards: dict[str, ClipCard] = {}
        self._active_clip_id: str | None = None
        self._build_ui()
        self.refresh()

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(36, 28, 36, 28)
        outer.setSpacing(20)

        header = QHBoxLayout()
        title = QLabel("Музыка / Клипы")
        title.setObjectName("h1")
        header.addWidget(title)
        header.addStretch(1)

        refresh_btn = QPushButton("Обновить")
        refresh_btn.setObjectName("ghost")
        refresh_btn.clicked.connect(self.refresh)
        header.addWidget(refresh_btn)
        outer.addLayout(header)

        subtitle = QLabel("Скачанные клипы. Нажмите «Поставить на обои», чтобы клип заиграл фоном на рабочем столе.")
        subtitle.setObjectName("muted")
        subtitle.setWordWrap(True)
        outer.addWidget(subtitle)

        # Scrollable list of cards
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        self.list_host = QWidget()
        self.list_layout = QVBoxLayout(self.list_host)
        self.list_layout.setContentsMargins(0, 0, 0, 0)
        self.list_layout.setSpacing(12)

        self.empty_label = QLabel(
            "Библиотека пуста.\nПерейдите во вкладку «Загрузка» и добавьте первое видео."
        )
        self.empty_label.setObjectName("muted")
        self.empty_label.setAlignment(Qt.AlignCenter)
        self.empty_label.setStyleSheet("padding: 80px 0;")
        self.list_layout.addWidget(self.empty_label)
        self.list_layout.addStretch(1)

        self.scroll.setWidget(self.list_host)
        outer.addWidget(self.scroll, 1)

    # ---------- public API ----------
    def refresh(self) -> None:
        # Remove all rows except the trailing stretch
        for i in reversed(range(self.list_layout.count())):
            item = self.list_layout.itemAt(i)
            w = item.widget() if item is not None else None
            if w is None:
                continue
            if w is self.empty_label:
                continue
            w.setParent(None)
        self._cards.clear()

        clips = [c for c in self.library.all() if c.exists()]
        # Drop missing-on-disk clips silently
        for c in self.library.all():
            if not c.exists():
                self.library.remove(c.id)

        if not clips:
            self.empty_label.show()
            return
        self.empty_label.hide()

        # Insert cards before the trailing stretch
        for clip in clips:
            card = ClipCard(clip)
            card.activate_requested.connect(self.activate_requested.emit)
            card.deactivate_requested.connect(self.deactivate_requested.emit)
            card.delete_requested.connect(self._on_delete)
            card.open_folder_requested.connect(self._on_open_folder)
            self.list_layout.insertWidget(self.list_layout.count() - 1, card)
            self._cards[clip.id] = card
            if clip.id == self._active_clip_id:
                card.set_active(True)

    def set_active_clip(self, clip_id: str | None) -> None:
        self._active_clip_id = clip_id
        for cid, card in self._cards.items():
            card.set_active(cid == clip_id)

    # ---------- internal ----------
    def _on_delete(self, clip_id: str) -> None:
        clip = self.library.get(clip_id)
        if clip is None:
            return
        ans = QMessageBox.question(
            self,
            "Удалить клип",
            f"Удалить «{clip.title}» из библиотеки и с диска?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        delete_files = ans == QMessageBox.Yes
        self.library.remove(clip_id, delete_files=delete_files)
        if self._active_clip_id == clip_id:
            self.deactivate_requested.emit(clip_id)
        self.refresh()

    def _on_open_folder(self, clip_id: str) -> None:
        clip = self.library.get(clip_id)
        if clip is None:
            return
        p = Path(clip.file)
        if not p.exists():
            return
        if sys.platform == "win32":
            subprocess.Popen(["explorer", "/select,", str(p)])
        elif sys.platform == "darwin":
            subprocess.Popen(["open", "-R", str(p)])
        else:
            subprocess.Popen(["xdg-open", str(p.parent)])
        _ = os  # keep import used
