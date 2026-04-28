# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for ytwall.
#
# Build with:  pyinstaller ytwall.spec --clean --noconfirm
#
# Place mpv-2.dll next to this spec (or in scripts/) and PyInstaller will
# bundle it into dist/ytwall/. Without mpv-2.dll the wallpaper engine refuses
# to start; the rest of the UI still works.

from pathlib import Path
from PyInstaller.utils.hooks import collect_submodules

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

# Bundle libmpv if user dropped it next to the spec
for dll_name in ("mpv-2.dll", "libmpv-2.dll"):
    dll_path = ROOT / dll_name
    if dll_path.exists():
        binaries.append((str(dll_path), "."))

hiddenimports = []
hiddenimports += collect_submodules("yt_dlp")

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
