from __future__ import annotations

import json
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path

from .config import app_data_dir


@dataclass
class Clip:
    id: str
    title: str
    artist: str
    url: str
    file: str  # absolute path to media file
    thumbnail: str | None  # absolute path to image, or None
    duration: float = 0.0
    width: int = 0
    height: int = 0
    added_at: float = field(default_factory=time.time)

    @property
    def path(self) -> Path:
        return Path(self.file)

    def exists(self) -> bool:
        return self.path.exists()


def _library_path() -> Path:
    return app_data_dir() / "library.json"


class Library:
    def __init__(self) -> None:
        self._clips: dict[str, Clip] = {}
        self.load()

    # ---------- persistence ----------
    def load(self) -> None:
        path = _library_path()
        if not path.exists():
            self._clips = {}
            return
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            self._clips = {}
            return
        clips: dict[str, Clip] = {}
        fields = set(Clip.__dataclass_fields__)
        for entry in data.get("clips", []):
            clean = {k: v for k, v in entry.items() if k in fields}
            try:
                clip = Clip(**clean)
            except TypeError:
                continue
            clips[clip.id] = clip
        self._clips = clips

    def save(self) -> None:
        path = _library_path()
        payload = {"clips": [asdict(c) for c in self._clips.values()]}
        path.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
        )

    # ---------- operations ----------
    def all(self) -> list[Clip]:
        return sorted(self._clips.values(), key=lambda c: c.added_at, reverse=True)

    def get(self, clip_id: str) -> Clip | None:
        return self._clips.get(clip_id)

    def add(
        self,
        *,
        title: str,
        artist: str,
        url: str,
        file: str,
        thumbnail: str | None,
        duration: float = 0.0,
        width: int = 0,
        height: int = 0,
    ) -> Clip:
        clip = Clip(
            id=uuid.uuid4().hex,
            title=title or "Untitled",
            artist=artist or "",
            url=url,
            file=file,
            thumbnail=thumbnail,
            duration=duration,
            width=width,
            height=height,
        )
        self._clips[clip.id] = clip
        self.save()
        return clip

    def remove(self, clip_id: str, *, delete_files: bool = False) -> bool:
        clip = self._clips.pop(clip_id, None)
        if clip is None:
            return False
        if delete_files:
            for p in (clip.file, clip.thumbnail):
                if not p:
                    continue
                try:
                    Path(p).unlink(missing_ok=True)
                except OSError:
                    pass
        self.save()
        return True

    def update(self, clip: Clip) -> None:
        self._clips[clip.id] = clip
        self.save()
