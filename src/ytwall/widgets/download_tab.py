from __future__ import annotations

from PySide6.QtCore import Qt, QThreadPool, Signal
from PySide6.QtGui import QClipboard, QGuiApplication
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ..config import Settings
from ..downloader import DownloadJob, DownloadResult, is_youtube_url
from ..library import Library


class DownloadTab(QWidget):
    clip_added = Signal(object)  # Clip

    def __init__(self, settings: Settings, library: Library) -> None:
        super().__init__()
        self.settings = settings
        self.library = library
        self.pool = QThreadPool.globalInstance()
        self._job: DownloadJob | None = None
        self._build_ui()

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(36, 28, 36, 28)
        outer.setSpacing(20)

        title = QLabel("Загрузка из YouTube")
        title.setObjectName("h1")
        subtitle = QLabel("Вставьте ссылку — клип попадёт в вашу библиотеку и его можно будет поставить на обои.")
        subtitle.setObjectName("muted")
        subtitle.setWordWrap(True)
        outer.addWidget(title)
        outer.addWidget(subtitle)

        card = QFrame()
        card.setObjectName("card")
        cl = QVBoxLayout(card)
        cl.setContentsMargins(24, 24, 24, 24)
        cl.setSpacing(16)

        url_row = QHBoxLayout()
        url_row.setSpacing(10)

        self.url_edit = QLineEdit()
        self.url_edit.setPlaceholderText("https://www.youtube.com/watch?v=…")
        self.url_edit.setText(self.settings.last_url)
        self.url_edit.returnPressed.connect(self._on_download_clicked)

        paste_btn = QPushButton("Вставить")
        paste_btn.setObjectName("ghost")
        paste_btn.clicked.connect(self._paste_from_clipboard)

        url_row.addWidget(self.url_edit, 1)
        url_row.addWidget(paste_btn)
        cl.addLayout(url_row)

        opts_row = QHBoxLayout()
        opts_row.setSpacing(10)

        q_label = QLabel("Качество:")
        q_label.setObjectName("muted")
        self.quality_box = QComboBox()
        self.quality_box.addItems(["720p", "1080p", "1440p", "2160p", "best"])
        idx = self.quality_box.findText(self.settings.quality)
        if idx >= 0:
            self.quality_box.setCurrentIndex(idx)

        self.download_btn = QPushButton("Скачать")
        self.download_btn.setObjectName("primary")
        self.download_btn.clicked.connect(self._on_download_clicked)

        self.cancel_btn = QPushButton("Отмена")
        self.cancel_btn.setObjectName("danger")
        self.cancel_btn.setEnabled(False)
        self.cancel_btn.clicked.connect(self._on_cancel_clicked)

        opts_row.addWidget(q_label)
        opts_row.addWidget(self.quality_box)
        opts_row.addStretch(1)
        opts_row.addWidget(self.cancel_btn)
        opts_row.addWidget(self.download_btn)
        cl.addLayout(opts_row)

        self.progress = QProgressBar()
        self.progress.setRange(0, 1000)
        self.progress.setValue(0)
        self.progress.setTextVisible(True)
        self.progress.setFormat("Готов")
        cl.addWidget(self.progress)

        self.status_label = QLabel("")
        self.status_label.setObjectName("muted")
        self.status_label.setWordWrap(True)
        cl.addWidget(self.status_label)

        outer.addWidget(card)
        outer.addStretch(1)

    # ---------- actions ----------
    def _paste_from_clipboard(self) -> None:
        cb: QClipboard = QGuiApplication.clipboard()
        text = (cb.text() or "").strip()
        if text:
            self.url_edit.setText(text)
            self.url_edit.setFocus()

    def _on_download_clicked(self) -> None:
        url = self.url_edit.text().strip()
        if not is_youtube_url(url):
            self.status_label.setObjectName("error")
            self.status_label.style().unpolish(self.status_label)
            self.status_label.style().polish(self.status_label)
            self.status_label.setText("Это не ссылка YouTube. Вставьте полный URL.")
            return

        self.settings.last_url = url
        self.settings.quality = self.quality_box.currentText()
        self.settings.save()

        self._set_busy(True)
        self.progress.setValue(0)
        self.progress.setFormat("Старт…")
        self.status_label.setObjectName("muted")
        self.status_label.style().unpolish(self.status_label)
        self.status_label.style().polish(self.status_label)
        self.status_label.setText("")

        from pathlib import Path

        job = DownloadJob(url, Path(self.settings.clips_dir), self.settings.quality)
        job.signals.progress.connect(self._on_progress, Qt.QueuedConnection)
        job.signals.finished.connect(self._on_finished, Qt.QueuedConnection)
        job.signals.failed.connect(self._on_failed, Qt.QueuedConnection)
        self._job = job
        self.pool.start(job)

    def _on_cancel_clicked(self) -> None:
        if self._job is not None:
            self._job.cancel()
            self.cancel_btn.setEnabled(False)

    # ---------- signals ----------
    def _on_progress(self, frac: float, msg: str) -> None:
        self.progress.setValue(int(frac * 1000))
        self.progress.setFormat(msg)

    def _on_finished(self, result: DownloadResult) -> None:
        clip = self.library.add(
            title=result.title,
            artist=result.artist,
            url=result.url,
            file=result.file,
            thumbnail=result.thumbnail,
            duration=result.duration,
            width=result.width,
            height=result.height,
        )
        self.clip_added.emit(clip)
        self._set_busy(False)
        self.progress.setValue(1000)
        self.progress.setFormat("Готово")
        self.status_label.setObjectName("success")
        self.status_label.style().unpolish(self.status_label)
        self.status_label.style().polish(self.status_label)
        self.status_label.setText(f"«{clip.title}» добавлен в библиотеку.")

    def _on_failed(self, error: str) -> None:
        self._set_busy(False)
        self.progress.setValue(0)
        self.progress.setFormat("Ошибка")
        self.status_label.setObjectName("error")
        self.status_label.style().unpolish(self.status_label)
        self.status_label.style().polish(self.status_label)
        self.status_label.setText(error)

    def _set_busy(self, busy: bool) -> None:
        self.download_btn.setEnabled(not busy)
        self.cancel_btn.setEnabled(busy)
        self.url_edit.setEnabled(not busy)
        self.quality_box.setEnabled(not busy)
