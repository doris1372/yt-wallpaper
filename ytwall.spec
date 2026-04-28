# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for ytwall.
#
# Build with:  pyinstaller ytwall.spec --clean --noconfirm
#
# Place mpv-2.dll next to this spec (or in scripts/) and PyInstaller will
# bundle it into dist/ytwall/. Without mpv-2.dll the wallpaper engine refuses
# to start; the rest of the UI still works.

from pathlib import Path
from PyInstaller.utils.hooks import collect_submodules, collect_data_files

block_cipher = None

ROOT = Path(SPECPATH).resolve()

datas = []
binaries = []

# Bundle assets if present
assets_dir = ROOT / "assets"
if assets_dir.exists():
    for f in assets_dir.iterdir():
        if f.is_file():
            datas.append((str(f), "assets"))

# Bundle libmpv. We only ship one copy (libmpv-2.dll) — python-mpv tries both
# names so this is enough.
for dll_name in ("libmpv-2.dll", "mpv-2.dll"):
    dll_path = ROOT / dll_name
    if dll_path.exists():
        binaries.append((str(dll_path), "."))
        break

# Bundle ffmpeg + ffprobe (required by yt-dlp to mux video+audio streams).
# Place ffmpeg.exe / ffprobe.exe next to this spec OR under bin/.
for exe_name in ("ffmpeg.exe", "ffprobe.exe", "ffmpeg", "ffprobe"):
    for parent in (ROOT, ROOT / "bin"):
        exe_path = parent / exe_name
        if exe_path.exists():
            binaries.append((str(exe_path), "."))
            break

# yt_dlp uses dynamic imports for hundreds of extractors — bundle them all.
hiddenimports = collect_submodules("yt_dlp")

# Make sure PySide6 / mpv are seen even when the entry point uses lazy imports.
hiddenimports += [
    "ytwall",
    "ytwall.app",
    "ytwall.config",
    "ytwall.library",
    "ytwall.downloader",
    "ytwall.wallpaper",
    "ytwall.pause_monitor",
    "ytwall.tray",
    "ytwall.styles",
    "ytwall.autostart",
    "ytwall.soundcloud",
    "ytwall.music_player",
    "ytwall.playlists",
    "ytwall.artwork",
    "ytwall.widgets",
    "ytwall.widgets.main_window",
    "ytwall.widgets.download_tab",
    "ytwall.widgets.library_tab",
    "ytwall.widgets.settings_tab",
    "ytwall.widgets.clip_card",
    "ytwall.widgets.music_tab",
    "ytwall.widgets.mini_player",
    "ytwall.widgets.track_row",
    "PySide6.QtCore",
    "PySide6.QtGui",
    "PySide6.QtWidgets",
    "mpv",
    "psutil",
]

# yt-dlp also ships a small set of data files (certifi etc.) — collect them.
datas += collect_data_files("yt_dlp", includes=["**/*.json"])

a = Analysis(
    ["src/ytwall/__main__.py"],
    pathex=[str(ROOT / "src")],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=["PyQt5", "PyQt6", "tkinter", "test", "unittest"],
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="ytwall",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    icon=str(ROOT / "assets" / "icon.ico") if (ROOT / "assets" / "icon.ico").exists() else None,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="ytwall",
)
