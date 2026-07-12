# PyInstaller onedir definition; build from the repository root.
a = Analysis(["src/rangebot/engine/main.py"], pathex=["src"], datas=[])
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, a.binaries, a.datas, name="bot-engine", console=True)
coll = COLLECT(exe, a.binaries, a.datas, name="bot-engine")
