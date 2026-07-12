# PyInstaller onedir definition; the UI remains separate from the engine build.
from pathlib import Path

project_root = Path(SPECPATH).parent
a = Analysis(
    [str(project_root / "src" / "rangebot" / "ui" / "main.py")],
    pathex=[str(project_root / "src")],
    datas=[
        (
            str(project_root / "src" / "rangebot" / "assets" / "fonts"),
            "rangebot/assets/fonts",
        )
    ],
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="rangebot-control",
    console=False,
)
coll = COLLECT(exe, a.binaries, a.datas, name="rangebot-control")
