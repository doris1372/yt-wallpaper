from __future__ import annotations

import json
import os
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path


def app_data_dir() -> Path:
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    out = base / "ytwall"
    out.mkdir(parents=True, exist_ok=True)
    return out


def default_clips_dir() -> Path:
    if sys.platform == "win32":
        base = Path(os.environ.get("USERPROFILE", Path.home())) / "Videos" / "ytwall"
    else:
        base = Path.home() / "Videos" / "ytwall"
    base.mkdir(parents=True, exist_ok=True)
    return base


@dataclass
class Settings:
    clips_dir: str = field(default_factory=lambda: str(default_clips_dir()))
    volume: int = 0  # 0..100; default muted because it's a wallpaper
    pause_on_fullscreen: bool = True
    pause_on_battery: bool = True
    pause_when_obscured: bool = True
    autostart: bool = False
    quality: str = "1080p"  # 720p / 1080p / 1440p / 2160p / best
    active_clip_id: str | None = None
    last_url: str = ""
    # Browser to read cookies from when YouTube asks for sign-in.
    # "auto" = try chrome/edge/firefox/brave/opera/vivaldi/chromium in order.
    # "off" = never use cookies. Specific name = only that browser.
    cookies_browser: str = "auto"

    @classmethod
    def load(cls) -> Settings:
        path = app_data_dir() / "settings.json"
        if path.exists():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                fields = {f for f in cls.__dataclass_fields__}
                clean = {k: v for k, v in data.items() if k in fields}
                return cls(**clean)
            except (OSError, json.JSONDecodeError, TypeError):
                pass
        return cls()

    def save(self) -> None:
        path = app_data_dir() / "settings.json"
        path.write_text(
            json.dumps(asdict(self), indent=2, ensure_ascii=False), encoding="utf-8"
        )
