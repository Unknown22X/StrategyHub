from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DETAIL = ROOT / "frontend" / "src" / "components" / "StrategyDetailPage.tsx"


def test_strategy_page_leads_with_operations_before_configuration() -> None:
    source = DETAIL.read_text(encoding="utf-8")
    styles = (ROOT / "frontend" / "src" / "styles.css").read_text(encoding="utf-8")
    docs = (ROOT / "docs" / "strategy-workflow.md").read_text(encoding="utf-8")

    command_index = source.index("Strategy command center")
    readiness_index = source.index("Strategy start readiness")
    configuration_index = source.index('tab === "configuration"')
    assert command_index < readiness_index < configuration_index
    for label in (
        "Realized PnL",
        "Win Rate",
        "Realized Drawdown",
        "Current Position",
        "Open Orders",
        "Recent activity",
    ):
        assert label in source
    assert "loadMarketSnapshot" in source
    assert "loadDashboard" in source
    assert "instance_id === strategy.instance_id" in source
    assert "calculateRealizedDrawdown" in source
    assert ".strategy-operations-grid" in styles
    assert "Missing attribution is displayed as unavailable" in docs
