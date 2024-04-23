# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['rlnexto_python\\main.py'],
    pathex=[],
    binaries=[('rlnexto_python/memory_writer/memory_writer.pyd', 'memory_writer')],
    datas=[('rlnexto_python/nexto', 'nexto'), ('rlnexto_python/nexto/nexto-model.pt', 'rlnexto_python/nexto'), ('rlnexto_python/necto', 'necto'), ('rlnexto_python/necto/necto-model.pt', 'rlnexto_python/necto'),  ('rlnexto_python/seer', 'seer'),  ('rlnexto_python/seer/Seer.pt', 'rlnexto_python/seer')],
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
