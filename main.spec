# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['rlmarlbot\\main.py'],
    pathex=[],
    binaries=[('rlmarlbot/memory_writer/memory_writer.pyd', 'memory_writer')],
    datas=[
        ('rlmarlbot/nexto', 'nexto'), 
        ('rlmarlbot/nexto/nexto-model.pt', 'rlmarlbot/nexto'), 
        ('rlmarlbot/necto', 'necto'),
        ('rlmarlbot/necto/necto-model.pt', 'rlmarlbot/necto'),  
        ('rlmarlbot/seer', 'seer'),  
        ('rlmarlbot/seer/Seer.pt', 'rlmarlbot/seer'),
        ('rlmarlbot/element', 'element'),  
        ('rlmarlbot/element/model.p', 'rlmarlbot/element'),
        ('rlmarlbot/helpers.py', '.')

    ],
    hiddenimports=['torch', 'rlgym_compat', 'sklearn'],
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
    name='main',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
