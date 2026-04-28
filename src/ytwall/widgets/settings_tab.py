from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from ..config import Settings


class SettingsTab(QWidget):
    settings_changed = Signal()
    volume_changed = Signal(int)
    pause_options_changed = Signal()

    def __init__(self, settings: Settings) -> None:
        super().__init__()
        self.settings = settings
        self._build_ui()

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(36, 28, 36, 28)
        outer.setSpacing(20)

        title = QLabel("Настройки")
        title.setObjectName("h1")
        outer.addWidget(title)

        # ---- Storage card ----
        card = QFrame()
        card.setObjectName("card")
        cl = QVBoxLayout(card)
        cl.setContentsMargins(24, 24, 24, 24)
        cl.setSpacing(14)

        cl.addWidget(self._h2("Хранилище"))
        path_row = QHBoxLayout()
        self.path_edit = QLineEdit(self.settings.clips_dir)
        self.path_edit.setReadOnly(True)
        browse = QPushButton("Выбрать…")
        browse.setObjectName("ghost")
        browse.clicked.connect(self._browse_dir)
        path_row.addWidget(self.path_edit, 1)
        path_row.addWidget(browse)
        cl.addLayout(path_row)

        cl.addWidget(self._h2("Качество скачивания"))
        self.quality_box = QComboBox()
        self.quality_box.addItems(["720p", "1080p", "1440p", "2160p", "best"])
        idx = self.quality_box.findText(self.settings.quality)
        if idx >= 0:
            self.quality_box.setCurrentIndex(idx)
        self.quality_box.currentTextChanged.connect(self._on_quality_changed)
        cl.addWidget(self.quality_box)

        cl.addWidget(self._h2("Cookies из браузера"))
        cookies_hint = QLabel(
            "Если YouTube требует подтвердить, что ты не бот — приложение возьмёт cookies "
            "из выбранного браузера. «Авто» пробует Chrome → Edge → Firefox → Brave → Opera."
        )
        cookies_hint.setObjectName("muted")
        cookies_hint.setWordWrap(True)
        cl.addWidget(cookies_hint)
        self.cookies_box = QComboBox()
        self._cookies_options = [
            ("auto", "Авто (рекомендуется)"),
            ("chrome", "Chrome"),
            ("edge", "Edge"),
            ("firefox", "Firefox"),
            ("brave", "Brave"),
            ("opera", "Opera"),
            ("vivaldi", "Vivaldi"),
            ("chromium", "Chromium"),
            ("off", "Не использовать"),
        ]
        for _, label in self._cookies_options:
            self.cookies_box.addItem(label)
        keys = [k for k, _ in self._cookies_options]
        cur_idx = keys.index(self.settings.cookies_browser) if self.settings.cookies_browser in keys else 0
        self.cookies_box.setCurrentIndex(cur_idx)
        self.cookies_box.currentIndexChanged.connect(self._on_cookies_changed)
        cl.addWidget(self.cookies_box)

        outer.addWidget(card)

        # ---- Playback card ----
        card2 = QFrame()
        card2.setObjectName("card")
        cl2 = QVBoxLayout(card2)
        cl2.setContentsMargins(24, 24, 24, 24)
        cl2.setSpacing(14)

        cl2.addWidget(self._h2("Воспроизведение"))

        vol_row = QHBoxLayout()
        vol_row.addWidget(QLabel("Громкость"))
        self.volume_slider = QSlider(Qt.Horizontal)
        self.volume_slider.setRange(0, 100)
        self.volume_slider.setValue(self.settings.volume)
        self.volume_slider.valueChanged.connect(self._on_volume_changed)
        self.volume_label = QLabel(f"{self.settings.volume}%")
        self.volume_label.setObjectName("muted")
        self.volume_label.setMinimumWidth(48)
        vol_row.addWidget(self.volume_slider, 1)
        vol_row.addWidget(self.volume_label)
        cl2.addLayout(vol_row)

        outer.addWidget(card2)

        # ---- Optimization card ----
        card3 = QFrame()
        card3.setObjectName("card")
        cl3 = QVBoxLayout(card3)
        cl3.setContentsMargins(24, 24, 24, 24)
        cl3.setSpacing(10)

        cl3.addWidget(self._h2("Оптимизация"))
        sub = QLabel(
            "Обои автоматически ставятся на паузу, когда вы не на рабочем столе — экономим батарею и GPU."
        )
        sub.setObjectName("muted")
        sub.setWordWrap(True)
        cl3.addWidget(sub)

        self.cb_fullscreen = QCheckBox("Пауза при полноэкранном приложении (игры, видео)")
        self.cb_fullscreen.setChecked(self.settings.pause_on_fullscreen)
        self.cb_fullscreen.toggled.connect(self._on_pause_changed)
        cl3.addWidget(self.cb_fullscreen)

        self.cb_obscured = QCheckBox("Пауза, когда окно поверх закрывает рабочий стол")
        self.cb_obscured.setChecked(self.settings.pause_when_obscured)
        self.cb_obscured.toggled.connect(self._on_pause_changed)
        cl3.addWidget(self.cb_obscured)

        self.cb_battery = QCheckBox("Пауза при работе от батареи")
        self.cb_battery.setChecked(self.settings.pause_on_battery)
        self.cb_battery.toggled.connect(self._on_pause_changed)
        cl3.addWidget(self.cb_battery)

        outer.addWidget(card3)

        # ---- Misc ----
        card4 = QFrame()
        card4.setObjectName("card")
        cl4 = QVBoxLayout(card4)
        cl4.setContentsMargins(24, 24, 24, 24)

        self.cb_autostart = QCheckBox("Запускать вместе с Windows")
        self.cb_autostart.setChecked(self.settings.autostart)
        self.cb_autostart.toggled.connect(self._on_autostart_changed)
        cl4.addWidget(self.cb_autostart)

        outer.addWidget(card4)
        outer.addStretch(1)

    def _h2(self, text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("h2")
        return label

    # ---------- handlers ----------
    def _browse_dir(self) -> None:
        path = QFileDialog.getExistingDirectory(
            self, "Выберите папку для клипов", self.settings.clips_dir
        )
        if path:
            self.settings.clips_dir = str(Path(path))
            self.path_edit.setText(self.settings.clips_dir)
            self.settings.save()
            self.settings_changed.emit()

    def _on_quality_changed(self, text: str) -> None:
        self.settings.quality = text
        self.settings.save()

    def _on_cookies_changed(self, idx: int) -> None:
        if 0 <= idx < len(self._cookies_options):
            self.settings.cookies_browser = self._cookies_options[idx][0]
            self.settings.save()

    def _on_volume_changed(self, value: int) -> None:
        self.settings.volume = int(value)
        self.volume_label.setText(f"{value}%")
        self.settings.save()
        self.volume_changed.emit(int(value))

    def _on_pause_changed(self) -> None:
        self.settings.pause_on_fullscreen = self.cb_fullscreen.isChecked()
        self.settings.pause_when_obscured = self.cb_obscured.isChecked()
        self.settings.pause_on_battery = self.cb_battery.isChecked()
        self.settings.save()
        self.pause_options_changed.emit()

    def _on_autostart_changed(self, checked: bool) -> None:
        self.settings.autostart = bool(checked)
        self.settings.save()
        try:
            from ..autostart import set_autostart

            set_autostart(checked)
        except Exception:  # noqa: BLE001
            pass
