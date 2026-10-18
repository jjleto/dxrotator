# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['/Users/luigigiusti/dxrotator/run_dxrotator.py'],
    pathex=['/Users/luigigiusti/dxrotator'],
    binaries=[],
    datas=[],
    hiddenimports=['serial.tools.list_ports'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['PySide6.QtWebEngineCore', 'PySide6.QtWebEngineWidgets', 'PySide6.Qt3DCore', 'PySide6.QtMultimedia', 'PySide6.QtQuick', 'tkinter'],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='DXRotator',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['/Users/luigigiusti/dxrotator/icon.icns'],
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='DXRotator',
)
app = BUNDLE(
    coll,
    name='DXRotator.app',
    icon='/Users/luigigiusti/dxrotator/icon.icns',
    bundle_identifier='org.iw5dnz.dxrotator',
)
