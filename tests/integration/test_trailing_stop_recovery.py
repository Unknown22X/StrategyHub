from datetime import UTC, datetime, timedelta
from decimal import Decimal

from fastapi.testclient import TestClient

from rangebot.domain.exchange import (
    ExchangeOperationResult,
    ExchangePositionSnapshot,
    ExchangeSnapshot,
)
from rangebot.domain.strategy import TradeOwnershipCreate
from rangebot.engine.api import create_app


class RecoveryAdapter:
    def __init__(
        self,
        *,
        active_trail_id: str | None = None,
        reconciliation_ready: bool = True,
        recovery_accepts: bool = True,
        position_open: bool = True,
        cancellation_accepts: bool = True,
    ) -> None:
        self.active_trail_id = active_trail_id
        self.reconciliation_ready = reconciliation_ready
        self.recovery_accepts = recovery_accepts
        self.position_open = position_open
        self.cancellation_accepts = cancellation_accepts
        self.recovery_calls = []
        self.cancellation_calls = []

    def reconcile(self, mode):
        return ExchangeSnapshot(
            mode=mode,
            reconciled_at=datetime.now(UTC),
            available_futures_balance=Decimal("900"),
            total_futures_balance=Decimal("1000"),
            total_futures_equity=Decimal("1000"),
            position_quantity=Decimal("2") if self.position_open else Decimal("0"),
            positions=(
                (
                    ExchangePositionSnapshot(
                        contract="BTC_USDT",
                        side="long",
                        quantity=Decimal("2"),
                        entry_price=Decimal("100"),
                    ),
                )
                if self.position_open
                else ()
            ),
            one_way_confirmed=True,
            cross_margin_confirmed=True,
            leverage_confirmed=5,
            risk_ready=True,
            daily_baseline_ready=True,
            protection_ready=True,
            trailing_protection_ready=(
                True if self.active_trail_id is not None else None
            ),
            trailing_reconciliation_ready=self.reconciliation_ready,
            trailing_order_ids=(self.active_trail_id,) if self.active_trail_id else (),
        )

    def ensure_trailing_protection(self, mode, request):
        self.recovery_calls.append((mode, request))
        if not self.recovery_accepts:
            return ExchangeOperationResult(
                accepted=False,
                client_request_id=request.client_request_id,
                message_ar="تعذر الاستعادة في الاختبار.",
            )
        self.active_trail_id = "recovered-trail"
        return ExchangeOperationResult(
            accepted=True,
            client_request_id=request.client_request_id,
            order_id=self.active_trail_id,
            message_ar="تمت الاستعادة.",
        )

    def cancel_trailing_protection(self, mode, order_id):
        self.cancellation_calls.append((mode, order_id))
        if not self.cancellation_accepts:
            return ExchangeOperationResult(
                accepted=False,
                client_request_id=f"cancel-trail-{order_id}",
                message_ar="تعذر إلغاء وقف التتبع في الاختبار.",
            )
        self.active_trail_id = None
        return ExchangeOperationResult(
            accepted=True,
            client_request_id=f"cancel-trail-{order_id}",
            message_ar="تم إلغاء وقف التتبع.",
        )


def _seed_desired_ownership(app) -> None:
    app.state.strategy_instance_repository.record_trade_ownership(
        TradeOwnershipCreate(
            identity_kind="position",
            external_identity="testnet:BTC_USDT:long",
            origin="manual",
            environment="testnet",
            symbol="BTC_USDT",
            direction="long",
            trailing_stop_price=Decimal("95"),
            trailing_stop_distance=Decimal("5"),
            trailing_state="desired",
            trailing_updated_at=datetime.now(UTC) - timedelta(minutes=1),
        )
    )


def _seed_active_ownership(app, order_id: str) -> None:
    app.state.strategy_instance_repository.record_trade_ownership(
        TradeOwnershipCreate(
            identity_kind="position",
            external_identity="testnet:BTC_USDT:long",
            origin="manual",
            environment="testnet",
            symbol="BTC_USDT",
            direction="long",
            trailing_stop_price=Decimal("95"),
            trailing_stop_distance=Decimal("5"),
            trailing_state="active",
            trailing_order_id=order_id,
            trailing_updated_at=datetime.now(UTC) - timedelta(minutes=1),
        )
    )


def test_missing_gate_trail_is_recovered_and_persisted_after_restart(tmp_path) -> None:
    adapter = RecoveryAdapter()
    app = create_app(
        f"sqlite:///{tmp_path / 'rangebot.db'}",
        exchange_adapter=adapter,
        exchange_adapter_mode="testnet",
    )
    with TestClient(app) as client:
        _seed_desired_ownership(app)
        response = client.post("/v1/exchange/testnet/reconcile")
        ownership = app.state.strategy_instance_repository.trade_ownership(
            "position", "testnet:BTC_USDT:long"
        )

    assert response.status_code == 200
    assert len(adapter.recovery_calls) == 1
    _, request = adapter.recovery_calls[0]
    assert request.quantity == Decimal("2")
    assert request.trailing_stop_distance == Decimal("5")
    assert ownership is not None
    assert ownership.trailing_state == "active"
    assert ownership.trailing_order_id == "recovered-trail"
    assert ownership.trailing_last_error is None


def test_existing_gate_trail_is_adopted_without_duplicate_submission(tmp_path) -> None:
    adapter = RecoveryAdapter(active_trail_id="existing-trail")
    app = create_app(
        f"sqlite:///{tmp_path / 'rangebot.db'}",
        exchange_adapter=adapter,
        exchange_adapter_mode="testnet",
    )
    with TestClient(app) as client:
        _seed_desired_ownership(app)
        client.post("/v1/exchange/testnet/reconcile")
        ownership = app.state.strategy_instance_repository.trade_ownership(
            "position", "testnet:BTC_USDT:long"
        )

    assert adapter.recovery_calls == []
    assert ownership is not None
    assert ownership.trailing_state == "active"
    assert ownership.trailing_order_id == "existing-trail"


def test_trail_list_outage_defers_recovery_without_duplicate_order(tmp_path) -> None:
    adapter = RecoveryAdapter(reconciliation_ready=False)
    app = create_app(
        f"sqlite:///{tmp_path / 'rangebot.db'}",
        exchange_adapter=adapter,
        exchange_adapter_mode="testnet",
    )
    with TestClient(app) as client:
        _seed_desired_ownership(app)
        client.post("/v1/exchange/testnet/reconcile")
        ownership = app.state.strategy_instance_repository.trade_ownership(
            "position", "testnet:BTC_USDT:long"
        )

    assert adapter.recovery_calls == []
    assert ownership is not None
    assert ownership.trailing_state == "desired"


def test_failed_trailing_recovery_records_error_without_changing_fixed_protection(tmp_path) -> None:
    adapter = RecoveryAdapter(recovery_accepts=False)
    app = create_app(
        f"sqlite:///{tmp_path / 'rangebot.db'}",
        exchange_adapter=adapter,
        exchange_adapter_mode="testnet",
    )
    with TestClient(app) as client:
        _seed_desired_ownership(app)
        response = client.post("/v1/exchange/testnet/reconcile")
        ownership = app.state.strategy_instance_repository.trade_ownership(
            "position", "testnet:BTC_USDT:long"
        )

    assert response.status_code == 200
    assert response.json()["snapshot"]["protection_ready"] is True
    assert ownership is not None
    assert ownership.trailing_state == "error"
    assert ownership.trailing_order_id is None
    assert ownership.trailing_last_error == "تعذر الاستعادة في الاختبار."


def test_confirmed_position_close_cancels_trail_and_clears_ownership(tmp_path) -> None:
    adapter = RecoveryAdapter(active_trail_id="123456", position_open=False)
    app = create_app(
        f"sqlite:///{tmp_path / 'rangebot.db'}",
        exchange_adapter=adapter,
        exchange_adapter_mode="testnet",
    )
    with TestClient(app) as client:
        _seed_active_ownership(app, "123456")
        response = client.post("/v1/exchange/testnet/reconcile")
        ownership = app.state.strategy_instance_repository.trade_ownership(
            "position", "testnet:BTC_USDT:long"
        )

    assert response.status_code == 200
    assert adapter.cancellation_calls == [("testnet", "123456")]
    assert response.json()["snapshot"]["trailing_order_ids"] == []
    assert response.json()["snapshot"]["trailing_protection_ready"] is None
    assert ownership is None


def test_confirmed_close_infers_single_trail_when_id_was_not_persisted(tmp_path) -> None:
    adapter = RecoveryAdapter(active_trail_id="123456", position_open=False)
    app = create_app(
        f"sqlite:///{tmp_path / 'rangebot.db'}",
        exchange_adapter=adapter,
        exchange_adapter_mode="testnet",
    )
    with TestClient(app) as client:
        _seed_desired_ownership(app)
        response = client.post("/v1/exchange/testnet/reconcile")
        ownership = app.state.strategy_instance_repository.trade_ownership(
            "position", "testnet:BTC_USDT:long"
        )

    assert response.status_code == 200
    assert adapter.cancellation_calls == [("testnet", "123456")]
    assert response.json()["snapshot"]["trailing_order_ids"] == []
    assert ownership is None


def test_failed_close_cleanup_keeps_durable_ownership_and_error(tmp_path) -> None:
    adapter = RecoveryAdapter(
        active_trail_id="123456",
        position_open=False,
        cancellation_accepts=False,
    )
    app = create_app(
        f"sqlite:///{tmp_path / 'rangebot.db'}",
        exchange_adapter=adapter,
        exchange_adapter_mode="testnet",
    )
    with TestClient(app) as client:
        _seed_active_ownership(app, "123456")
        response = client.post("/v1/exchange/testnet/reconcile")
        ownership = app.state.strategy_instance_repository.trade_ownership(
            "position", "testnet:BTC_USDT:long"
        )

    assert response.status_code == 200
    assert adapter.cancellation_calls == [("testnet", "123456")]
    assert response.json()["snapshot"]["trailing_order_ids"] == ["123456"]
    assert response.json()["snapshot"]["trailing_reconciliation_ready"] is False
    assert response.json()["snapshot"]["trailing_protection_ready"] is False
    assert ownership is not None
    assert ownership.trailing_state == "error"
    assert ownership.trailing_order_id == "123456"
    assert ownership.trailing_last_error == "تعذر إلغاء وقف التتبع في الاختبار."
