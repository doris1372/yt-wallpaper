"""Music tab — search SoundCloud, browse charts, 'My wave', and playlists."""
from __future__ import annotations

import logging
import random

from PySide6.QtCore import QObject, QRunnable, Qt, QThreadPool, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from ..music_player import MusicPlayer
from ..playlists import Playlists
from ..soundcloud import SoundCloudClient, SoundCloudError, Track
from .track_row import TrackList

log = logging.getLogger(__name__)


class _SearchSignals(QObject):
    done = Signal(list, str)  # tracks, mode-tag
    failed = Signal(str)


class _SearchJob(QRunnable):
    def __init__(self, sc: SoundCloudClient, mode: str, query: str = "") -> None:
        super().__init__()
        self.sc = sc
        self.mode = mode
        self.query = query
        self.signals = _SearchSignals()

    def run(self) -> None:  # type: ignore[override]
        try:
            if self.mode == "search":
                tracks = self.sc.search(self.query, limit=30)
            elif self.mode == "charts":
                tracks = self.sc.charts(limit=50)
            else:
                tracks = []
            self.signals.done.emit(tracks, self.mode)
        except SoundCloudError as e:
            self.signals.failed.emit(str(e))
        except Exception as e:  # noqa: BLE001
            self.signals.failed.emit(f"{type(e).__name__}: {e}")


class _WaveSeedJob(QRunnable):
    """Build a 'My Wave' queue: pick a random seed and follow related tracks."""

    def __init__(self, sc: SoundCloudClient, seed_hint: list[Track] | None = None) -> None:
        super().__init__()
        self.sc = sc
        self.seed_hint = seed_hint or []
        self.signals = _SearchSignals()

    def run(self) -> None:  # type: ignore[override]
        try:
            seeds = list(self.seed_hint)
            if not seeds:
                # Use trending charts as the universe of seed candidates.
                seeds = self.sc.charts(limit=50)
            if not seeds:
                self.signals.failed.emit("Не получилось построить волну: нет seed-треков")
                return
            seed = random.choice(seeds)
            related = self.sc.related(seed.id, limit=20)
            queue = [seed] + [t for t in related if t.id != seed.id]
            self.signals.done.emit(queue, "wave")
        except SoundCloudError as e:
            self.signals.failed.emit(str(e))
        except Exception as e:  # noqa: BLE001
            self.signals.failed.emit(f"{type(e).__name__}: {e}")


class MusicTab(QWidget):
    def __init__(
        self,
        sc_client: SoundCloudClient,
        player: MusicPlayer,
        playlists: Playlists,
    ) -> None:
        super().__init__()
        self.sc = sc_client
        self.player = player
        self.playlists = playlists
        self.pool = QThreadPool.globalInstance()

        self._build_ui()

    # ---------- UI ----------
    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(28, 24, 28, 12)
        outer.setSpacing(16)

        title = QLabel("Музыка")
        title.setObjectName("h1")
        outer.addWidget(title)

        # ---- top toolbar with search + mode buttons ----
        toolbar = QHBoxLayout()
        toolbar.setSpacing(8)
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Найти трек, артиста или альбом на SoundCloud…")
        self.search_edit.returnPressed.connect(self._do_search)
        toolbar.addWidget(self.search_edit, 1)

        self.search_btn = QPushButton("Искать")
        self.search_btn.setObjectName("primary")
        self.search_btn.clicked.connect(self._do_search)
        toolbar.addWidget(self.search_btn)
        outer.addLayout(toolbar)

        modes = QHBoxLayout()
        modes.setSpacing(8)
        self._mode_btns: dict[str, QPushButton] = {}
        for key, label in [
            ("search", "Поиск"),
            ("charts", "Чарты"),
            ("wave", "Моя волна"),
            ("playlists", "Плейлисты"),
        ]:
            btn = QPushButton(label)
            btn.setCheckable(True)
            btn.setObjectName("mode")
            btn.clicked.connect(lambda _checked, k=key: self._set_mode(k))
            modes.addWidget(btn)
            self._mode_btns[key] = btn
        modes.addStretch(1)
        outer.addLayout(modes)

        # ---- content stack ----
        self.stack = QStackedWidget()
        outer.addWidget(self.stack, 1)

        # search/charts/wave share one TrackList
        self.track_list = TrackList()
        self.track_list.play_clicked.connect(self._on_play)
        self.track_list.add_to_playlist_clicked.connect(self._on_add_to_playlist)
        self.track_list.set_wallpaper_clicked.connect(self._on_set_wallpaper)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setWidget(self.track_list)
        self._tracks_index = self.stack.addWidget(scroll)

        # status / empty state widget
        self.status_label = QLabel("Введи запрос или открой Чарты / Мою волну.")
        self.status_label.setObjectName("muted")
        self.status_label.setAlignment(Qt.AlignCenter)
        self._status_index = self.stack.addWidget(self.status_label)

        # playlists view
        self.playlists_view = _PlaylistsView(self.playlists, self.player, self.sc)
        self.playlists_view.set_wallpaper_request.connect(self.set_wallpaper_request.emit)
        self._playlists_index = self.stack.addWidget(self.playlists_view)

        self._set_mode("charts")

    # ---------- mode handling ----------
    def _set_mode(self, mode: str) -> None:
        for key, btn in self._mode_btns.items():
            btn.setChecked(key == mode)
        self._current_mode = mode
        if mode == "playlists":
            self.stack.setCurrentIndex(self._playlists_index)
            self.playlists_view.refresh()
            return
        if mode == "search":
            q = self.search_edit.text().strip()
            if not q:
                self.status_label.setText("Введи запрос в поле выше и нажми Enter.")
                self.stack.setCurrentIndex(self._status_index)
                return
            self._run(_SearchJob(self.sc, "search", q))
            self._show_loading("Ищу на SoundCloud…")
            return
        if mode == "charts":
            self._run(_SearchJob(self.sc, "charts"))
            self._show_loading("Загружаю чарты…")
            return
        if mode == "wave":
            self._run(_WaveSeedJob(self.sc))
            self._show_loading("Подбираю «Мою волну»…")
            return

    def _do_search(self) -> None:
        q = self.search_edit.text().strip()
        if not q:
            return
        self._set_mode("search")

    def _show_loading(self, msg: str) -> None:
        self.status_label.setText(msg)
        self.stack.setCurrentIndex(self._status_index)

    def _run(self, job: _SearchJob | _WaveSeedJob) -> None:
        job.signals.done.connect(self._on_results, Qt.QueuedConnection)
        job.signals.failed.connect(self._on_failed, Qt.QueuedConnection)
        self.pool.start(job)

    def _on_results(self, tracks: list[Track], mode: str) -> None:
        if not tracks:
            self.status_label.setText("Ничего не нашлось :(")
            self.stack.setCurrentIndex(self._status_index)
            return
        self.track_list.set_tracks(tracks)
        self.stack.setCurrentIndex(self._tracks_index)
        if mode == "wave":
            # Auto-start wave: queue all results, mark seed for endless-wave appending.
            self.player.set_queue(tracks, start_index=0, wave_seed=tracks[0])

    def _on_failed(self, err: str) -> None:
        self.status_label.setText(f"Ошибка: {err}")
        self.stack.setCurrentIndex(self._status_index)

    # ---------- track row actions ----------
    def _on_play(self, track: Track) -> None:
        # Build a queue from current visible list (so user can press play on any
        # row and the rest queues up after).
        rows = self._visible_tracks()
        if track in rows:
            idx = rows.index(track)
            self.player.set_queue(rows, start_index=idx, wave_seed=None)
        else:
            self.player.play_track(track)

    def _visible_tracks(self) -> list[Track]:
        out: list[Track] = []
        layout = self.track_list._layout
        for i in range(layout.count() - 1):
            w = layout.itemAt(i).widget()
            if w is not None and hasattr(w, "track"):
                out.append(w.track)
        return out

    def _on_add_to_playlist(self, track: Track) -> None:
        items = self.playlists.all()
        names = [p.name for p in items] + ["+ Новый плейлист…"]
        choice, ok = QInputDialog.getItem(
            self, "Добавить в плейлист", "Выберите плейлист:", names, 0, False
        )
        if not ok:
            return
        if choice == "+ Новый плейлист…" or not items:
            name, ok = QInputDialog.getText(self, "Новый плейлист", "Название:")
            if not ok or not name.strip():
                return
            pl = self.playlists.create(name.strip())
        else:
            pl = items[names.index(choice)]
        self.playlists.add_track(pl.id, track)
        QMessageBox.information(self, "Готово", f"Трек добавлен в «{pl.name}».")

    def _on_set_wallpaper(self, track: Track) -> None:
        # Forwarded to controller via the player's signal in app.py — but we
        # also expose a direct emit so the controller can hook in.
        self.set_wallpaper_request.emit(track)

    set_wallpaper_request = Signal(object)


class _PlaylistsView(QWidget):
    def __init__(self, playlists: Playlists, player: MusicPlayer, sc: SoundCloudClient) -> None:
        super().__init__()
        self.playlists = playlists
        self.player = player
        self.sc = sc
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        # left column: playlist list + new button
        left_col = QVBoxLayout()
        new_btn = QPushButton("+ Новый плейлист")
        new_btn.setObjectName("primary")
        new_btn.clicked.connect(self._create)
        left_col.addWidget(new_btn)

        self.list_widget = QListWidget()
        self.list_widget.setObjectName("playlistList")
        self.list_widget.itemSelectionChanged.connect(self._on_select)
        self.list_widget.setContextMenuPolicy(Qt.CustomContextMenu)
        self.list_widget.customContextMenuRequested.connect(self._show_context_menu)
        left_col.addWidget(self.list_widget, 1)
        left_wrap = QWidget()
        left_wrap.setLayout(left_col)
        left_wrap.setFixedWidth(240)
        layout.addWidget(left_wrap)

        # right: tracks of selected playlist
        self.tracks_view = TrackList()
        self.tracks_view.play_clicked.connect(self._on_play_track)
        self.tracks_view.add_to_playlist_clicked.connect(self._on_add_to)
        self.tracks_view.set_wallpaper_clicked.connect(self._on_set_wallpaper)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setWidget(self.tracks_view)
        layout.addWidget(scroll, 1)

    def refresh(self) -> None:
        self.list_widget.clear()
        for p in self.playlists.all():
            item = QListWidgetItem(f"{p.name}  ({len(p.tracks)})")
            item.setData(Qt.UserRole, p.id)
            self.list_widget.addItem(item)
        if self.list_widget.count() > 0 and self.list_widget.currentRow() < 0:
            self.list_widget.setCurrentRow(0)

    def _create(self) -> None:
        name, ok = QInputDialog.getText(self, "Новый плейлист", "Название:")
        if not ok or not name.strip():
            return
        self.playlists.create(name.strip())
        self.refresh()

    def _on_select(self) -> None:
        item = self.list_widget.currentItem()
        if item is None:
            return
        pl = self.playlists.get(item.data(Qt.UserRole))
        if pl is None:
            return
        self.tracks_view.set_tracks([t.to_track() for t in pl.tracks])

    def _on_play_track(self, track: Track) -> None:
        item = self.list_widget.currentItem()
        if item is None:
            return
        pl = self.playlists.get(item.data(Qt.UserRole))
        if pl is None:
            return
        all_tracks = [t.to_track() for t in pl.tracks]
        idx = next((i for i, t in enumerate(all_tracks) if t.id == track.id), 0)
        self.player.set_queue(all_tracks, start_index=idx)

    def _on_add_to(self, track: Track) -> None:
        QMessageBox.information(self, "Информация", "Трек уже находится в плейлисте.")

    set_wallpaper_request = Signal(object)

    def _on_set_wallpaper(self, track: Track) -> None:
        self.set_wallpaper_request.emit(track)

    def _show_context_menu(self, pos) -> None:
        item = self.list_widget.itemAt(pos)
        if item is None:
            return
        pl = self.playlists.get(item.data(Qt.UserRole))
        if pl is None:
            return
        menu = QMenu(self)
        menu.addAction("Переименовать", lambda: self._rename(pl.id))
        menu.addAction("Удалить", lambda: self._delete(pl.id))
        menu.exec(self.list_widget.mapToGlobal(pos))

    def _rename(self, pid: str) -> None:
        pl = self.playlists.get(pid)
        if pl is None:
            return
        new, ok = QInputDialog.getText(self, "Переименовать", "Новое название:", text=pl.name)
        if ok and new.strip():
            self.playlists.rename(pid, new.strip())
            self.refresh()

    def _delete(self, pid: str) -> None:
        pl = self.playlists.get(pid)
        if pl is None:
            return
        if QMessageBox.question(self, "Удалить", f"Удалить «{pl.name}»?") == QMessageBox.Yes:
            self.playlists.delete(pid)
            self.refresh()
