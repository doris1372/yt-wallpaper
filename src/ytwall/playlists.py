"""Local playlists of SoundCloud tracks.

Persists to ``%APPDATA%\\ytwall\\playlists.json``.
Each playlist holds a list of *track snapshots* (id + title + artist + cover
+ duration + permalink) so playlists work fully offline; we only re-fetch
the streaming URL when actually playing.
"""
from __future__ import annotations

import json
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path

from .config import app_data_dir
from .soundcloud import Track


@dataclass
class TrackSnapshot:
    id: int
    title: str
    artist: str
    duration_ms: int
    permalink_url: str
    artwork_url: str | None

    @classmethod
    def from_track(cls, t: Track) -> TrackSnapshot:
        return cls(
            id=t.id,
            title=t.title,
            artist=t.artist,
            duration_ms=t.duration_ms,
            permalink_url=t.permalink_url,
            artwork_url=t.display_artwork or t.artwork_url,
        )

    def to_track(self) -> Track:
        return Track(
            id=self.id,
            title=self.title,
            artist=self.artist,
            duration_ms=self.duration_ms,
            permalink_url=self.permalink_url,
            artwork_url=self.artwork_url,
            waveform_url=None,
            genre="",
            raw={},
        )


@dataclass
class Playlist:
    id: str
    name: str
    tracks: list[TrackSnapshot] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)


def _playlists_path() -> Path:
    return app_data_dir() / "playlists.json"


class Playlists:
    def __init__(self) -> None:
        self._items: dict[str, Playlist] = {}
        self.load()

    def load(self) -> None:
        path = _playlists_path()
        if not path.exists():
            self._items = {}
            return
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            self._items = {}
            return
        out: dict[str, Playlist] = {}
        for raw in data.get("playlists", []):
            try:
                tracks = [TrackSnapshot(**t) for t in raw.get("tracks", [])]
                pl = Playlist(
                    id=str(raw.get("id") or uuid.uuid4().hex),
                    name=str(raw.get("name") or "Без имени"),
                    tracks=tracks,
                    created_at=float(raw.get("created_at") or time.time()),
                )
                out[pl.id] = pl
            except (TypeError, ValueError):
                continue
        self._items = out

    def save(self) -> None:
        path = _playlists_path()
        payload = {
            "playlists": [
                {
                    "id": p.id,
                    "name": p.name,
                    "tracks": [asdict(t) for t in p.tracks],
                    "created_at": p.created_at,
                }
                for p in self._items.values()
            ]
        }
        path.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
        )

    def all(self) -> list[Playlist]:
        return sorted(self._items.values(), key=lambda p: p.created_at, reverse=True)

    def get(self, playlist_id: str) -> Playlist | None:
        return self._items.get(playlist_id)

    def create(self, name: str) -> Playlist:
        pl = Playlist(id=uuid.uuid4().hex, name=name or "Новый плейлист")
        self._items[pl.id] = pl
        self.save()
        return pl

    def rename(self, playlist_id: str, name: str) -> bool:
        pl = self._items.get(playlist_id)
        if pl is None:
            return False
        pl.name = name or pl.name
        self.save()
        return True

    def delete(self, playlist_id: str) -> bool:
        if self._items.pop(playlist_id, None) is None:
            return False
        self.save()
        return True

    def add_track(self, playlist_id: str, track: Track) -> bool:
        pl = self._items.get(playlist_id)
        if pl is None:
            return False
        if any(t.id == track.id for t in pl.tracks):
            return True  # already in playlist
        pl.tracks.append(TrackSnapshot.from_track(track))
        self.save()
        return True

    def remove_track(self, playlist_id: str, track_id: int) -> bool:
        pl = self._items.get(playlist_id)
        if pl is None:
            return False
        before = len(pl.tracks)
        pl.tracks = [t for t in pl.tracks if t.id != track_id]
        if len(pl.tracks) == before:
            return False
        self.save()
        return True
