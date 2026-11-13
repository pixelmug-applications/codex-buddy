# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path

block_cipher = None
ROOT_DIR = Path(SPECPATH).parent

a = Analysis(
    [str(ROOT_DIR / 'packaging/pyinstaller_app_entry.py')],
    pathex=[str(ROOT_DIR)],
    binaries=[],
    datas=[
        (str(ROOT_DIR / 'assets/status-icon.png'), 'assets'),
        (str(ROOT_DIR / 'assets/status-icon@2x.png'), 'assets'),
    ],
    hiddenimports=['rumps', 'AppKit', 'Foundation', 'objc', 'src'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='PixelMug Codex',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
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
    name='PixelMug Codex',
)
app = BUNDLE(
    coll,
    name='PixelMug Codex.app',
    icon=str(ROOT_DIR / 'assets/pixelmug-codex.icns'),
    bundle_identifier='com.pixelmug.codex',
    info_plist={
        'LSUIElement': True,
        'CFBundleName': 'PixelMug Codex',
        'CFBundleDisplayName': 'PixelMug Codex',
        'NSHighResolutionCapable': True,
    },
)
