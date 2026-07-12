from decimal import Decimal

from hypothesis import given
from hypothesis import strategies as st

from rangebot.domain.entry_preview import EntryPreviewRequest, create_entry_preview


def _request(**overrides: object) -> EntryPreviewRequest:
    values: dict[str, object] = {
        "available_futures_balance": Decimal("1000"),
        "allocation_percentage": Decimal("100"),
        "safety_reserve_percentage": Decimal("0"),
        "leverage": 10,
        "expected_entry_price": Decimal("100"),
        "quantity_step": Decimal("0.001"),
        "minimum_quantity": Decimal("0.001"),
        "direction": "long",
        "quote_revision": "quote-1",
    }
    values.update(overrides)
    return EntryPreviewRequest(**values)


def test_preview_uses_fallback_fees_and_rounds_down_before_final_check() -> None:
    preview = create_entry_preview(_request(expected_entry_price=Decimal("333.33")))

    assert preview.fee_source == "fallback"
    assert preview.quantity % Decimal("0.001") == Decimal("0")
    assert preview.total_required <= Decimal("1000")
    assert preview.can_submit is True
    assert preview.estimated_liquidation_label == "Paper estimated liquidation"
    assert preview.take_profit_price is not None
    assert preview.stop_loss_price is not None


def test_preview_rejects_minimum_quantity_and_invalid_allocation_option() -> None:
    too_small = create_entry_preview(
        _request(available_futures_balance=Decimal("1"), minimum_quantity=Decimal("1"))
    )

    assert too_small.can_submit is False
    assert "minimum_quantity" in too_small.blocking_reasons
    try:
        _request(allocation_percentage=Decimal("60"))
    except ValueError:
        pass
    else:
        raise AssertionError("Unsupported allocation percentage was accepted.")


@given(
    balance=st.decimals(min_value="1", max_value="100000", places=2),
    price=st.decimals(min_value="1", max_value="100000", places=2),
    allocation=st.sampled_from([Decimal("25"), Decimal("50"), Decimal("75"), Decimal("100")]),
)
def test_sizing_never_exceeds_available_futures_balance(
    balance: Decimal, price: Decimal, allocation: Decimal
) -> None:
    preview = create_entry_preview(
        _request(
            available_futures_balance=balance,
            expected_entry_price=price,
            allocation_percentage=allocation,
        )
    )

    assert preview.total_required <= balance
