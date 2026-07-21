from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / "frontend" / "src" / "components" / "WorkflowPages.tsx"


def test_opportunities_review_shortlist_ignore_and_instance_creation_are_explicit() -> (
    None
):
    source = WORKFLOW.read_text(encoding="utf-8")
    app = (ROOT / "frontend" / "src" / "App.tsx").read_text(encoding="utf-8")
    styles = (ROOT / "frontend" / "src" / "styles.css").read_text(encoding="utf-8")

    assert "Opportunity Review" in source
    assert "Opportunity shortlisted only. No Strategy was started." in source
    assert "Show ignored/history" in source
    assert "Undo Ignore" in source
    assert "Create Strategy Instance for this coin" in source
    assert "Create Paper Strategy Instance" in source
    assert "scanner unavailable" in source
    assert "does not claim the chosen Strategy discovered the coin" in source
    assert "createStrategyFromTemplate" in source
    assert "onOpenStrategy" in source + app
    assert ".opportunity-review-panel" in styles
