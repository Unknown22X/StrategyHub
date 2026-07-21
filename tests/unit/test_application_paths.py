from pathlib import Path

from sqlalchemy.engine import make_url

from rangebot.engine.paths import application_paths, default_database_url


def test_application_paths_use_absolute_override_and_create_required_directories(
    tmp_path: Path, monkeypatch
) -> None:
    home = tmp_path / "Range Bot بيانات"
    monkeypatch.setenv("RANGEBOT_HOME", str(home))

    paths = application_paths()

    assert paths.root == home.resolve()
    assert paths.data == paths.root / "data"
    assert paths.config == paths.root / "config"
    assert paths.logs == paths.root / "logs"
    assert paths.backup == paths.root / "backup"
    assert paths.runtime == paths.root / "runtime"
    assert all(path.is_absolute() and path.is_dir() for path in paths.directories())


def test_default_database_url_points_to_local_application_data(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("RANGEBOT_HOME", str(tmp_path / "app-home"))

    database_url = default_database_url()
    database_path = Path(make_url(database_url).database)

    assert database_url.startswith("sqlite:///")
    assert database_path.parent.name == "data"
    assert database_path.name == "rangebot.db"
