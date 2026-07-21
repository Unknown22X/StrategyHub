from io import BytesIO
from zipfile import ZipFile

from fastapi.testclient import TestClient

from rangebot.engine.api import create_app


def test_support_log_api_returns_a_downloadable_sanitized_zip(tmp_path) -> None:
    logs = tmp_path / "logs"
    logs.mkdir()
    (logs / "engine.log").write_text("engine healthy\n", encoding="utf-8")
    database_url = f"sqlite:///{tmp_path / 'rangebot.db'}"

    with TestClient(create_app(database_url, log_directory=logs)) as client:
        response = client.post("/v1/logs/export")

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/zip"
    assert "rangebot-support-" in response.headers["content-disposition"]
    with ZipFile(BytesIO(response.content)) as archive:
        assert archive.read("engine.log").decode("utf-8") == "engine healthy\n"
        assert "SUPPORT-ARCHIVE.txt" in archive.namelist()
