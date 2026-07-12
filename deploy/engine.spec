# PyInstaller onedir definition; build from the repository root.
from pathlib import Path

project_root = Path(SPECPATH).parent
a = Analysis(
    [str(project_root / "src" / "rangebot" / "engine" / "main.py")],
    pathex=[str(project_root / "src")],
    datas=[
        (
            str(project_root / "src" / "rangebot" / "engine" / "migrations"),
            "rangebot/engine/migrations",
        ),
        (str(project_root / "alembic.ini"), "."),
    ],
)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="bot-engine", console=True)
coll = COLLECT(exe, a.binaries, a.datas, name="bot-engine")
