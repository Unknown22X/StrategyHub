from fastapi.testclient import TestClient

from rangebot.engine.api import create_app


def test_frontend_is_mounted_when_compiled_assets_exist(tmp_path) -> None:
    database_url = f"sqlite:///{tmp_path / 'rangebot.db'}"
    frontend_dist = tmp_path / "frontend-dist"
    assets = frontend_dist / "assets"
    assets.mkdir(parents=True)
    (frontend_dist / "index.html").write_text(
        '<!doctype html><html lang="ar" dir="rtl"><body>RangeBot Dashboard</body></html>',
        encoding="utf-8",
    )
    (assets / "app.js").write_text("console.log('rangebot');", encoding="utf-8")

    with TestClient(create_app(database_url, frontend_dist=frontend_dist)) as client:
        dashboard = client.get("/app/")
        asset = client.get("/app/assets/app.js")
        health = client.get("/health")

    assert dashboard.status_code == 200
    assert "RangeBot Dashboard" in dashboard.text
    assert asset.status_code == 200
    assert "rangebot" in asset.text
    assert health.status_code == 200


def test_frontend_mount_is_optional_when_assets_are_missing(tmp_path) -> None:
    database_url = f"sqlite:///{tmp_path / 'rangebot.db'}"
    missing_dist = tmp_path / "missing-dist"

    with TestClient(create_app(database_url, frontend_dist=missing_dist)) as client:
        dashboard = client.get("/app/", follow_redirects=False)
        health = client.get("/health")

    assert dashboard.status_code == 404
    assert health.status_code == 200
