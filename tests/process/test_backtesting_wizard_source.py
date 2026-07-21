from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / "frontend" / "src" / "components" / "WorkflowPages.tsx"


def test_backtesting_wizard_has_beginner_preset_final_step_and_bounded_polling() -> (
    None
):
    source = WORKFLOW.read_text(encoding="utf-8")
    workflow_api = (ROOT / "frontend" / "src" / "workflowApi.ts").read_text(
        encoding="utf-8"
    )
    styles = (ROOT / "frontend" / "src" / "styles.css").read_text(encoding="utf-8")

    assert "Beginner — realistic and conservative" in source
    assert "Show advanced execution assumptions" in source
    assert "Final step" in source
    assert "No more setup steps." in source
    assert "Optional: pre-test hypothesis" in source
    assert "Optional: Open Setup Review" in source
    assert "Backtest polling timed out after 10 minutes" in source
    assert "consecutivePollFailures >= 3" in source
    assert "Cancel Backtest" in source
    assert "historyError" in source
    assert "failure_code" in source and "failure_stage" in source
    assert "timeoutMs" in workflow_api
    assert "cancelPortfolioBacktest" in workflow_api
    assert ".advanced-backtest-settings" in styles
