from importlib import invalidate_caches
from pathlib import Path

import pytest

from rangebot.domain.strategy import StrategyTypeMetadata
from rangebot.engine.strategy_registry import (
    StrategyRegistry,
    discover_strategy_registry,
)


def _metadata(type_id: str) -> StrategyTypeMetadata:
    return StrategyTypeMetadata(
        type_id=type_id,
        display_name_ar="استراتيجية اختبار",
        display_name_en="Test Strategy",
        description_ar="وصف صالح للاختبار.",
        description_en="A valid test description.",
        version="1",
    )


def test_builtin_registry_resolves_each_evaluator_by_type() -> None:
    registry = discover_strategy_registry()

    assert registry.evaluator("range").type_id == "range"
    assert registry.evaluator("adaptive_trend").type_id == "adaptive_trend"
    assert registry.evaluator("range_breakout").type_id == "range_breakout"


def test_builtin_strategy_metadata_declares_dynamic_runtime_capabilities() -> None:
    registry = discover_strategy_registry()

    for metadata in registry.list():
        assert metadata.implementation_status == "working"
        assert metadata.supported_timeframes
        assert all(timeframe > 0 for timeframe in metadata.supported_timeframes)
        assert "candlesticks" in metadata.required_market_data_feeds
        assert "last_price" in metadata.required_market_data_feeds
        assert metadata.supports_long is True
        if metadata.type_id == "fixed_price_ladder":
            assert metadata.supports_short is False
        else:
            assert metadata.supports_short is True

    assert registry.get("range").supported_timeframes == (5, 15, 60, 1440)


def test_registry_rejects_duplicate_type_ids() -> None:
    registry = StrategyRegistry()
    registry.register(_metadata("sample"))

    with pytest.raises(ValueError, match="already registered"):
        registry.register(_metadata("sample"))


def test_strategy_modules_are_discovered_without_registry_code_changes(
    tmp_path: Path, monkeypatch
) -> None:
    package = tmp_path / "sample_strategies"
    package.mkdir()
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "alpha.py").write_text(
        "STRATEGY_TYPE = {"
        "'type_id': 'alpha',"
        "'display_name_ar': 'ألفا',"
        "'display_name_en': 'Alpha',"
        "'description_ar': 'استراتيجية ألفا للاختبار.',"
        "'description_en': 'Alpha strategy for testing.',"
        "'version': '1'"
        "}\n",
        encoding="utf-8",
    )
    monkeypatch.syspath_prepend(str(tmp_path))
    invalidate_caches()

    registry = discover_strategy_registry("sample_strategies")

    assert [item.type_id for item in registry.list()] == ["alpha"]
    assert registry.get("alpha").display_name_en == "Alpha"
