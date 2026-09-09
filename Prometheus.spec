# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['Prometheus_V10_9_2.py'],
    pathex=['.'],
    binaries=[],
    datas=[],
    hiddenimports=[
        'prometheus_core',
        'prometheus_ui',
        'prometheus_ui.theme',
        'prometheus_ui.primitives',
        'prometheus_ui.widgets',
        'prometheus_ui.charts',
        'prometheus_ui.ttk_skin',
        'prometheus_ui.shell',
        'prometheus_ui.cbot_console',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='Prometheus Procurement',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
