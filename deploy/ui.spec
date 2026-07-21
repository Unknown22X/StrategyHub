# PyInstaller onedir definition for the localhost web-control launcher.
from pathlib import Path

project_root = Path(SPECPATH).parent
icon_path = project_root / "deploy" / "RangeBot.ico"
a = Analysis(
    [str(project_root / "src" / "rangebot" / "ui" / "main.py")],
    pathex=[str(project_root / "src")],
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="RangeBot",
    console=False,
    icon=str(icon_path) if icon_path.is_file() else None,
)
coll = COLLECT(exe, a.binaries, a.datas, name="RangeBot")
