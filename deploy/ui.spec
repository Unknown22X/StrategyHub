# PyInstaller onedir definition; the UI remains separate from the engine build.
a = Analysis(["src/rangebot/ui/main.py"], pathex=["src"], datas=[])
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, a.binaries, a.datas, name="rangebot-control", console=False)
coll = COLLECT(exe, a.binaries, a.datas, name="rangebot-control")
