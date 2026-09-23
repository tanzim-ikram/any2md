# -*- mode: python ; coding: utf-8 -*-

import os
from pathlib import Path
from PyInstaller.utils.hooks import collect_submodules, collect_data_files

block_cipher = None
project_root = Path.cwd()

datas = [
    (str(project_root / 'any2md' / 'resources'), 'any2md/resources'),
    (str(project_root / 'any2md' / 'ui' / 'style'), 'any2md/ui/style'),
    (str(project_root / 'Any2MD Logo.ico'), '.'),
    (str(project_root / 'Any2MD Logo.png'), '.'),
]

# Collect data files and submodules for all converter dependencies
hidden_imports = [
    'PyQt6.QtSvg',
    'PyQt6.QtCore',
    'PyQt6.QtGui',
    'PyQt6.QtWidgets',
    'any2md.platform.windows_context_menu',
    'any2md.conversion.to_markdown',
    'any2md.conversion.from_markdown',
    'any2md.conversion.engine',
    'any2md.conversion.worker',
    'any2md.storage.settings',
    'any2md.storage.history',
]

converter_packages = [
    'markitdown',
    'mammoth',
    'pdfminer',
    'pdfplumber',
    'pypdf',
    'docx',
    'pptx',
    'openpyxl',
    'bs4',
    'markdown',
]

for pkg in converter_packages:
    try:
        datas += collect_data_files(pkg)
    except Exception:
        pass
    try:
        hidden_imports += collect_submodules(pkg)
    except Exception:
        pass


a = Analysis(
    ['any2md/main.py'],
    pathex=[str(project_root)],
    binaries=[],
    datas=datas,
    hiddenimports=hidden_imports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['tkinter', 'matplotlib', 'numpy.distutils', 'scipy', 'IPython'],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='Any2MD',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(project_root / 'Any2MD Logo.ico'),
)

