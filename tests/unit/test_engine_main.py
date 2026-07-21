import sys
from pathlib import Path

from sqlalchemy.engine import make_url

from rangebot.engine import main as engine_main


def test_engine_cli_defaults_to_application_sqlite_database(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("RANGEBOT_HOME", str(tmp_path / "RangeBot"))
    monkeypatch.setattr(sys, "argv", ["rangebot-engine"])

    arguments = engine_main.parse_arguments()
    database_path = Path(make_url(arguments.database_url).database)

    assert arguments.database_url.startswith("sqlite:///")
    assert database_path.parent.name == "data"
    assert database_path.name == "rangebot.db"
    assert arguments.mode == "paper"


def test_live_mode_accepts_explicit_local_sqlite_database(
    tmp_path: Path, monkeypatch
) -> None:
    database_url = f"sqlite:///{tmp_path / 'live.db'}"
    monkeypatch.setenv("RANGEBOT_HOME", str(tmp_path / "RangeBot"))
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "rangebot-engine",
            "--mode",
            "live",
            "--database-url",
            database_url,
        ],
    )
    calls: dict[str, object] = {}
    adapter = object()
    monkeypatch.setattr(
        engine_main,
        "CredentialReloadingGateIoAdapter",
        lambda *args, **kwargs: (
            calls.update(adapter_arguments=(args, kwargs)) or adapter
        ),
    )
    monkeypatch.setattr(
        engine_main,
        "create_app",
        lambda supplied_url, **kwargs: (
            calls.update(database_url=supplied_url, **kwargs) or "app"
        ),
    )
    monkeypatch.setattr(
        engine_main.uvicorn,
        "run",
        lambda app, **kwargs: calls.update(app=app, uvicorn=kwargs),
    )

    engine_main.main()

    assert calls["database_url"] == database_url
    assert calls["initial_environment"] == "live"
    assert calls["enable_public_websocket"] is False
    assert calls["enable_private_websocket"] is False
    adapter_factory = calls["exchange_adapter_factory"]
    assert callable(adapter_factory)
    assert adapter_factory("live") is adapter  # type: ignore[operator]
    adapter_args, adapter_kwargs = calls["adapter_arguments"]
    assert adapter_args == ("live",)
    assert adapter_kwargs == {
        "enable_network": False,
        "enable_order_submission": False,
    }
    assert calls["app"] == "app"
    assert calls["uvicorn"]["host"] == "127.0.0.1"  # type: ignore[index]
