# -*- mode: python ; coding: utf-8 -*-
import sys
import os

block_cipher = None

a = Analysis(
    ['app.py'],
    pathex=['.'],
    binaries=[],
    datas=[
        ('web', 'web'),
        ('core/rpa/selectors', 'core/rpa/selectors'),
    ],
    hiddenimports=[
        'win32com',
        'win32com.client',
        'openpyxl',
        'pandas',
        'sqlite3',
        'webview',
        'clr',
        'pythonnet',
        'core.bridge',
        'core.storage',
        'core.analytics.engine',
        'core.rpa.runner',
        'core.rpa.base',
        'core.rpa.sap_session',
        'core.rpa.tasks.sap_zerar_compromisso',
        'core.rpa.tasks.sap_data_necessidade',
        'core.rpa.tasks.sap_concluir_requisicoes',
        'core.rpa.tasks.sap_eliminar_reserva',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['tkinter', 'matplotlib', 'scipy'],
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
    name='Mirandinha_v3.0.4',
    icon='web/assets/img/mirandinha.ico',
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
