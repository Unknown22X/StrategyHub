# PyInstaller onedir definition; build from the repository root.
from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules

project_root = Path(SPECPATH).parent
frontend_dist = project_root / "frontend" / "dist"
icon_path = project_root / "deploy" / "RangeBot.ico"
migrations_root = project_root / "src" / "rangebot" / "engine" / "migrations"
datas = [
    (
        str(migration_file),
        "rangebot/engine/migrations/" + migration_file.relative_to(migrations_root).parent.as_posix(),
    )
    for migration_file in migrations_root.rglob("*")
    if migration_file.is_file() and "__pycache__" not in migration_file.parts
]
datas += [
    (str(project_root / "alembic.ini"), "."),
]
if (frontend_dist / "index.html").is_file():
    datas.append((str(frontend_dist), "frontend/dist"))

a = Analysis(
    [str(project_root / "src" / "rangebot" / "engine" / "main.py")],
    pathex=[str(project_root / "src")],
    datas=datas,
    hiddenimports=collect_submodules("rangebot.strategies"),
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="bot-engine",
    console=True,
    hide_console="hide-early",
    icon=str(icon_path) if icon_path.is_file() else None,
)
coll = COLLECT(exe, a.binaries, a.datas, name="bot-engine")
