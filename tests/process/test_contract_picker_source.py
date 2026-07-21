from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
FRONTEND = ROOT / "frontend" / "src"


def test_contract_picker_search_manual_fallback_and_live_price_are_wired() -> None:
    picker = (FRONTEND / "components" / "ContractSymbolPicker.tsx").read_text(
        encoding="utf-8"
    )
    api = (FRONTEND / "api.ts").read_text(encoding="utf-8")
    create = (FRONTEND / "components" / "StrategyCreateDrawer.tsx").read_text(
        encoding="utf-8"
    )
    detail = (FRONTEND / "components" / "StrategyDetailPage.tsx").read_text(
        encoding="utf-8"
    )
    manual = (FRONTEND / "components" / "ManualTradeDrawer.tsx").read_text(
        encoding="utf-8"
    )
    workflow = (FRONTEND / "components" / "WorkflowPages.tsx").read_text(
        encoding="utf-8"
    )

    assert "/v1/paper/contracts" in api
    assert "Manual symbol — validation pending" in picker
    assert "loadMarketSnapshot" in picker
    assert "setInterval(refresh, 5000)" in picker
    assert "snapshot.source" in picker
    assert "snapshot.observed_at" in picker
    assert "snapshot.state" in picker
    assert "Gate public market" in picker
    assert "ContractSymbolPicker" in create
    assert "ContractSymbolPicker" in detail
    assert "ContractSymbolPicker" in manual
    assert "ContractSymbolPicker" in workflow
