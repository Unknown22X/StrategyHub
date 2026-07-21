from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
FRONTEND = ROOT / "frontend" / "src"


def test_strategy_lifecycle_is_exposed_in_api_sidebar_and_archived_page() -> None:
    api = (FRONTEND / "api.ts").read_text(encoding="utf-8")
    app = (FRONTEND / "App.tsx").read_text(encoding="utf-8")
    detail = (FRONTEND / "components" / "StrategyDetailPage.tsx").read_text(
        encoding="utf-8"
    )
    archived = (FRONTEND / "components" / "ArchivedStrategiesPage.tsx").read_text(
        encoding="utf-8"
    )
    styles = (FRONTEND / "styles.css").read_text(encoding="utf-8")
    docs = (ROOT / "docs" / "strategy-workflow.md").read_text(encoding="utf-8")

    assert "/v1/strategies/archived" in api
    assert "setStrategyPinned" in api
    assert 'pinned ? "pin" : "unpin"' in api
    assert "/archive" in api and "/restore" in api
    assert "/deletion-readiness" in api
    assert "Archived Strategies" in app
    assert "Pinned · Stopped" in app
    assert "Running" in app and "Paused" in app and "Error" in app
    assert "handlePin" in detail
    assert "handleArchive" in detail
    assert "Delete permanently" in detail
    assert "history ويجب إبقاؤها Archived" in archived
    assert ".strategy-state-dot.state-running" in styles
    assert ".strategy-state-dot.state-pinned" in styles
    assert "0035_strategy_instance_lifecycle" in docs
