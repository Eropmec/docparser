# -*- mode: python ; coding: utf-8 -*-

block_cipher = None

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=[
        'json',
        're',
        'tkinter',
        'tkinter.ttk',
        'tkinter.messagebox',
        'tkinter.filedialog',
        'tkinter.scrolledtext',
        'dataclasses',
        'typing'
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    # Исключаем тяжелые и ненужные библиотеки, включая llama_cpp (он подгрузится динамически, если установлен)
    excludes=['matplotlib', 'pandas', 'scipy', 'PIL', 'cv2', 'llama_cpp'],
    noarchive=False,
    optimize=0,
)

# ИСПРАВЛЕНИЕ: используем a.pure вместо устаревшего a.tree
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='DocParser',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
