from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
FRONTEND = ROOT / "frontend" / "src"


def test_template_preset_instance_contract_is_exposed_to_frontend() -> None:
    api = (FRONTEND / "api.ts").read_text(encoding="utf-8")
    workflow = (FRONTEND / "workflowApi.ts").read_text(encoding="utf-8")
    types = (FRONTEND / "types.ts").read_text(encoding="utf-8")
    docs = (ROOT / "docs" / "strategy-workflow.md").read_text(encoding="utf-8")

    assert "/v1/strategy-catalog/templates" in api
    assert "/v1/strategy-instances" in api
    assert "/v1/strategy-presets" in workflow
    assert "BuiltInStrategyTemplate" in types
    assert "StrategyInstanceFromTemplateCreate" in types
    assert "template_version" in types
    assert "preset_revision" in types
    assert "immutable" in types
    assert "legacy `/v1/strategy-templates` API remains a compatibility alias" in docs
