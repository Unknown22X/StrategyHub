from decimal import Decimal

import pytest

from rangebot.domain.orders import FuturesContractRules
from rangebot.strategies.fixed_price_ladder import (
    FixedPriceLadderConfig,
    FixedPriceLadderOrderPlanner,
    FixedPriceLadderRuntime,
    LadderFill,
    build_ladder_preview,
    calculate_take_profit_price,
    contract_quantity_for_margin,
    weighted_average_entry,
)


def _config(**overrides):
    value = {
        "contract_symbol": "BASED_USDT",
        "total_budget": "300",
        "take_profit_value": "5",
        "levels": [
            {"level_id": "l1", "price": "0.085", "display_order": 1},
            {"level_id": "l2", "price": "0.084", "display_order": 2},
            {"level_id": "l3", "price": "0.083", "display_order": 3},
        ],
    }
    value.update(overrides)
    return FixedPriceLadderConfig.model_validate(value)


def _rules() -> FuturesContractRules:
    return FuturesContractRules(
        symbol="BASED_USDT",
        contract_multiplier=Decimal("1"),
        quantity_step=Decimal("0.000000001"),
        minimum_quantity=Decimal("0.000000001"),
        price_step=Decimal("0.0000000001"),
        maximum_leverage=20,
        maker_fee_rate=Decimal("0"),
        taker_fee_rate=Decimal("0"),
    )


def test_equal_allocation_and_contract_rounding_never_exceed_margin_budget():
    config = _config()
    preview = build_ladder_preview(
        config,
        _rules(),
        available_balance=Decimal("300"),
        market_price=Decimal("0.086"),
        best_ask=Decimal("0.086"),
    )

    assert preview.can_activate is True
    assert [level.allocation for level in preview.levels] == [
        Decimal("100"),
        Decimal("100"),
        Decimal("100"),
    ]
    assert all(
        level.contract_quantity * level.price <= level.allocated_margin
        for level in preview.levels
    )
    assert preview.total_required_balance <= Decimal("300")


@pytest.mark.parametrize(
    ("method", "levels", "expected"),
    (
        (
            "custom_weights",
            [
                {
                    "level_id": "l1",
                    "price": "10",
                    "display_order": 1,
                    "allocation_weight": "50",
                },
                {
                    "level_id": "l2",
                    "price": "9",
                    "display_order": 2,
                    "allocation_weight": "30",
                },
                {
                    "level_id": "l3",
                    "price": "8",
                    "display_order": 3,
                    "allocation_weight": "20",
                },
            ],
            [Decimal("150"), Decimal("90"), Decimal("60")],
        ),
        (
            "custom_amounts",
            [
                {
                    "level_id": "l1",
                    "price": "10",
                    "display_order": 1,
                    "allocation_amount": "150",
                },
                {
                    "level_id": "l2",
                    "price": "9",
                    "display_order": 2,
                    "allocation_amount": "90",
                },
                {
                    "level_id": "l3",
                    "price": "8",
                    "display_order": 3,
                    "allocation_amount": "60",
                },
            ],
            [Decimal("150"), Decimal("90"), Decimal("60")],
        ),
    ),
)
def test_custom_allocations(method, levels, expected):
    config = _config(allocation_method=method, levels=levels)
    preview = build_ladder_preview(
        config,
        _rules().model_copy(update={"price_step": Decimal("1")}),
        available_balance=Decimal("300"),
        market_price=Decimal("11"),
        best_ask=Decimal("11"),
    )
    assert [level.allocation for level in preview.levels] == expected


def test_invalid_configuration_blocks_duplicate_or_wrongly_ordered_prices():
    with pytest.raises(ValueError, match="unique"):
        _config(
            levels=[
                {"level_id": "l1", "price": "1", "display_order": 1},
                {"level_id": "l2", "price": "1", "display_order": 2},
            ]
        )
    with pytest.raises(ValueError, match="highest to lowest"):
        _config(
            levels=[
                {"level_id": "l1", "price": "1", "display_order": 1},
                {"level_id": "l2", "price": "2", "display_order": 2},
            ]
        )


def test_weighted_average_and_price_tp_use_actual_fills():
    config = _config()
    fills = [
        LadderFill(
            fill_id="f1",
            level_id="l1",
            price=Decimal("0.085"),
            contract_quantity=Decimal("100") / Decimal("0.085"),
        ),
        LadderFill(
            fill_id="f2",
            level_id="l2",
            price=Decimal("0.084"),
            contract_quantity=Decimal("100") / Decimal("0.084"),
        ),
    ]
    average = weighted_average_entry(fills, Decimal("1"))
    target = calculate_take_profit_price(
        config,
        fills,
        contract_multiplier=Decimal("1"),
        price_tick=Decimal("0.0000000001"),
    )

    assert average == Decimal("0.08449704142011834319526627219")
    assert target == Decimal("0.0887218935")


def test_leverage_changes_size_but_not_price_percentage_target_and_changes_roi_target():
    fills_1x = [
        LadderFill(
            fill_id="f1",
            level_id="l1",
            price=Decimal("100"),
            contract_quantity=Decimal("1"),
        ),
    ]
    fills_5x = [
        LadderFill(
            fill_id="f1",
            level_id="l1",
            price=Decimal("100"),
            contract_quantity=Decimal("5"),
        ),
    ]
    config_1x = _config(
        total_budget="100",
        leverage=1,
        levels=[
            {"level_id": "l1", "price": "100", "display_order": 1},
            {"level_id": "l2", "price": "90", "display_order": 2},
        ],
    )
    config_5x = config_1x.model_copy(update={"leverage": 5})
    target_1x = calculate_take_profit_price(
        config_1x, fills_1x, contract_multiplier=Decimal("1"), price_tick=Decimal("1")
    )
    target_5x = calculate_take_profit_price(
        config_5x, fills_5x, contract_multiplier=Decimal("1"), price_tick=Decimal("1")
    )
    roi_5x = calculate_take_profit_price(
        config_5x.model_copy(
            update={"take_profit_mode": "roi_percentage_on_used_margin"}
        ),
        fills_5x,
        contract_multiplier=Decimal("1"),
        price_tick=Decimal("1"),
    )

    assert target_1x == target_5x == Decimal("105")
    assert roi_5x != target_5x
    assert contract_quantity_for_margin(
        Decimal("100"), Decimal("100"), 5, Decimal("1"), Decimal("1")
    ) == Decimal("5")


def test_preview_blocks_immediate_fill_and_unmanaged_state():
    preview = build_ladder_preview(
        _config(),
        _rules(),
        available_balance=Decimal("1000"),
        market_price=Decimal("0.086"),
        best_ask=Decimal("0.0845"),
        unmanaged_position=True,
    )
    assert preview.can_activate is False
    assert "unmanaged_position" in {issue.code for issue in preview.issues}
    assert "immediate_fill_not_allowed" in {issue.code for issue in preview.issues}


def test_duplicate_fill_is_idempotent_and_tp_request_is_reduce_only():
    runtime = FixedPriceLadderRuntime(_config(), _rules(), "cycle-1")
    fill = LadderFill(
        fill_id="fill-1",
        level_id="l1",
        price=Decimal("0.085"),
        contract_quantity=Decimal("1000"),
    )
    assert runtime.record_fill(fill) is True
    assert runtime.record_fill(fill) is False

    class FakeOrderManager:
        def __init__(self):
            self.calls = []

        def submit_automatic(self, request, **kwargs):
            self.calls.append((request, kwargs))
            return kwargs

    manager = FakeOrderManager()
    result = FixedPriceLadderOrderPlanner(runtime).submit_or_replace_take_profit(
        manager, instance_id="instance-1"
    )
    assert result is not None
    request, metadata = manager.calls[0]
    assert request.reduce_only is True
    assert request.direction == "short"
    assert metadata["order_role"] == "take_profit"
    assert metadata["strategy_type_id"] == "fixed_price_ladder"
