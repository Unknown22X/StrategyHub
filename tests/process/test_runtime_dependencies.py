from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_end_user_runtime_is_sqlite_only_and_does_not_bundle_desktop_ui_toolkit() -> None:
    project = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    runtime_section, development_section = project.split("[dependency-groups]", maxsplit=1)

    assert "psycopg" not in runtime_section.casefold()
    assert "postgres" not in runtime_section.casefold()
    assert "pyside" not in runtime_section.casefold()
    assert "PySide6-Essentials" in development_section
    assert "SQLAlchemy" in runtime_section
    assert "alembic" in runtime_section


def test_release_pipeline_does_not_package_retired_database_scripts() -> None:
    build = (ROOT / "build_release.bat").read_text(encoding="utf-8")
    installer = (ROOT / "deploy" / "RangeBot.iss").read_text(encoding="utf-8")

    assert "backup-postgresql" not in build + installer
    assert "restore-postgresql" not in build + installer
    assert "pg_dump" not in build + installer
    assert "pg_restore" not in build + installer
