from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
FRONTEND = ROOT / "frontend" / "src"


def test_frontend_exposes_start_readiness_backtest_warning_and_live_confirmation() -> (
    None
):
    api = (FRONTEND / "api.ts").read_text(encoding="utf-8")
    types = (FRONTEND / "types.ts").read_text(encoding="utf-8")
    detail = (FRONTEND / "components" / "StrategyDetailPage.tsx").read_text(
        encoding="utf-8"
    )
    app = (FRONTEND / "App.tsx").read_text(encoding="utf-8")
    docs = (ROOT / "docs" / "strategy-workflow.md").read_text(encoding="utf-8")

    assert "/start-readiness" in api
    assert "StrategyStartReadiness" in types
    assert "never_backtested" in types
    assert "current_successful" in types
    assert "current_failed" in types
    assert "Backtest stale" in detail
    assert "Never Backtested" in detail
    assert "START LIVE STRATEGY" in detail
    assert "START LIVE STRATEGY" in app
    assert "0034_strategy_run_configuration_snapshot" in docs
    assert "Backtesting is optional" in docs
