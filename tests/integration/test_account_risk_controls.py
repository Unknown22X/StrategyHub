from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from fastapi.testclient import TestClient

from rangebot.domain.account_risk import AccountRiskPolicyUpdate
from rangebot.domain.exchange import ExchangeSnapshot
from rangebot.domain.trades import TradeFillCreate
from rangebot.engine.account_risk import (
    AccountDailyRiskBaselineRepository,
    AccountRiskPolicyRepository,
    AccountRiskService,
)
from rangebot.engine.api import create_app
from rangebot.engine.database import apply_migrations, create_database_engine
from rangebot.engine.exchange import MockGateIoAdapter
from rangebot.engine.performance import AccountPerformanceRepository
from rangebot.engine.trade_history import TradeHistoryRepository


RIYADH = ZoneInfo("Asia/Riyadh")


@dataclass
class MutableClock:
    value: datetime

    def __call__(self) -> datetime:
        return self.value


def _service(database_url: str, clock: MutableClock):
    apply_migrations(database_url)
    engine = create_database_engine(database_url)
    policy = AccountRiskPolicyRepository(engine)
    baselines = AccountDailyRiskBaselineRepository(engine)
    performance = AccountPerformanceRepository(engine)
    trades = TradeHistoryRepository(engine)
    service = AccountRiskService(
        policy,
        baselines,
        performance,
        trades,
        now_factory=clock,
    )
    return policy, baselines, performance, trades, service


def _equity(
    mode: str,
    occurred_at: datetime,
    equity: str,
) -> ExchangeSnapshot:
    return ExchangeSnapshot(
        mode=mode,
        reconciled_at=occurred_at,
        total_futures_equity=Decimal(equity),
        available_futures_balance=Decimal(equity),
    )


def _fill(
    *,
    environment: str,
    trade_id: str,
    order_id: str,
    occurred_at: datetime,
    origin: str,
    position_effect: str = "open",
    realized_pnl: str | None = None,
) -> TradeFillCreate:
    return TradeFillCreate(
        environment=environment,
        external_trade_id=trade_id,
        order_id=order_id,
        contract="BTC_USDT",
        side="sell" if position_effect == "close" else "buy",
        position_effect=position_effect,
        quantity=Decimal("1"),
        price=Decimal("100"),
        fee=Decimal("0.05"),
        role="taker",
        close_quantity=Decimal("1") if position_effect == "close" else Decimal("0"),
        trade_value=Decimal("100"),
        realized_pnl=Decimal(realized_pnl) if realized_pnl is not None else None,
        occurred_at=occurred_at,
        source="gate_rest",
        origin=origin,
    )


def test_riyadh_baseline_is_immutable_and_environment_specific(tmp_path) -> None:
    database_url = f"sqlite:///{tmp_path / 'rangebot.db'}"
    clock = MutableClock(datetime(2026, 7, 21, 1, 0, tzinfo=UTC))
    _, baselines, performance, _, service = _service(database_url, clock)

    performance.record(_equity("testnet", clock.value - timedelta(minutes=20), "1000"))
    performance.record(_equity("testnet", clock.value - timedelta(minutes=10), "900"))
    first = service.status("testnet", synchronization_complete=True)

    performance.record(_equity("testnet", clock.value - timedelta(minutes=2), "1200"))
    second = service.status("testnet", synchronization_complete=True)
    duplicate_capture = baselines.capture_if_missing(
        environment="testnet",
        day=clock.value.astimezone(RIYADH).date(),
        baseline_equity=Decimal("9999"),
        captured_at=clock.value,
    )

    performance.record(_equity("live", clock.value - timedelta(minutes=5), "500"))
    live = service.status("live", synchronization_complete=True)

    assert first.baseline_equity == Decimal("1000")
    assert first.current_equity == Decimal("900")
    assert second.baseline_equity == Decimal("1000")
    assert second.current_equity == Decimal("1200")
    assert duplicate_capture.baseline_equity == Decimal("1000")
    assert live.baseline_equity == Decimal("500")
    assert live.environment == "live"
    assert first.environment == "testnet"


def test_new_riyadh_day_captures_a_new_baseline(tmp_path) -> None:
    database_url = f"sqlite:///{tmp_path / 'rangebot.db'}"
    clock = MutableClock(datetime(2026, 7, 20, 20, 50, tzinfo=UTC))
    _, baselines, performance, _, service = _service(database_url, clock)

    performance.record(_equity("testnet", clock.value - timedelta(minutes=10), "1000"))
    previous_day = service.status("testnet", synchronization_complete=True)

    clock.value = datetime(2026, 7, 20, 21, 10, tzinfo=UTC)
    performance.record(_equity("testnet", clock.value - timedelta(minutes=5), "900"))
    new_day = service.status("testnet", synchronization_complete=True)

    assert previous_day.day.isoformat() == "2026-07-20"
    assert previous_day.baseline_equity == Decimal("1000")
    assert new_day.day.isoformat() == "2026-07-21"
    assert new_day.baseline_equity == Decimal("900")
    assert baselines.get("testnet", previous_day.day) is not None
    assert baselines.get("testnet", new_day.day) is not None


def test_disabled_limits_are_explicit_and_do_not_fake_large_values(tmp_path) -> None:
    database_url = f"sqlite:///{tmp_path / 'rangebot.db'}"
    clock = MutableClock(datetime(2026, 7, 21, 1, 0, tzinfo=UTC))
    policy, _, _, trades, service = _service(database_url, clock)
    policy.update(
        AccountRiskPolicyUpdate(
            daily_loss_enabled=False,
            daily_loss_limit=Decimal("100"),
            losing_trade_enabled=False,
            losing_trade_limit=1,
            automatic_trade_enabled=False,
            automatic_trade_limit=1,
        )
    )
    trades.record(
        _fill(
            environment="testnet",
            trade_id="loss",
            order_id="loss-order",
            occurred_at=clock.value - timedelta(minutes=1),
            origin="manual",
            position_effect="close",
            realized_pnl="-10",
        )
    )
    trades.record(
        _fill(
            environment="testnet",
            trade_id="automatic",
            order_id="automatic-order",
            occurred_at=clock.value - timedelta(minutes=1),
            origin="automatic_strategy",
        )
    )

    status = service.status("testnet", synchronization_complete=True)

    assert status.risk_data_state == "account_data_unavailable"
    assert status.manual_entries_blocked is False
    assert status.automatic_entries_blocked is False
    assert status.blocked_reason_codes == ()
    assert [limit.state for limit in status.limits] == [
        "disabled",
        "disabled",
        "disabled",
    ]
    assert status.policy.daily_loss_limit == Decimal("100")
    assert status.policy.losing_trade_limit == 1
    assert status.policy.automatic_trade_limit == 1


def test_missing_baseline_and_sync_incomplete_never_claim_limit_reached(
    tmp_path,
) -> None:
    database_url = f"sqlite:///{tmp_path / 'rangebot.db'}"
    clock = MutableClock(datetime(2026, 7, 21, 1, 0, tzinfo=UTC))
    _, _, _, _, service = _service(database_url, clock)

    missing = service.status("live", synchronization_complete=True)
    synchronizing = service.status("live", synchronization_complete=False)

    assert missing.risk_data_state == "account_data_unavailable"
    assert missing.blocked_reason_codes == ("risk_data_unavailable",)
    assert missing.limits[0].state == "data_unavailable"
    assert synchronizing.risk_data_state == "synchronizing"
    assert synchronizing.blocked_reason_codes == ("synchronization_incomplete",)
    assert all(limit.state == "synchronizing" for limit in synchronizing.limits)
    for status in (missing, synchronizing):
        assert "daily_loss_limit_reached" not in status.blocked_reason_codes
        assert "losing_trade_limit_reached" not in status.blocked_reason_codes
        assert "automatic_trade_limit_reached" not in status.blocked_reason_codes


def test_live_disable_requires_explicit_real_funds_confirmation(tmp_path) -> None:
    database_url = f"sqlite:///{tmp_path / 'rangebot.db'}"
    app = create_app(
        database_url,
        exchange_adapter=MockGateIoAdapter(),
        exchange_adapter_mode="live",
    )
    update = {
        "daily_loss_enabled": False,
        "daily_loss_limit": "100",
        "losing_trade_enabled": True,
        "losing_trade_limit": 3,
        "automatic_trade_enabled": True,
        "automatic_trade_limit": 5,
    }

    with TestClient(app) as client:
        rejected = client.put("/v1/account-risk/policy", json=update)
        accepted = client.put(
            "/v1/account-risk/policy",
            json={**update, "confirmation": "DISABLE LIVE RISK LIMITS"},
        )

    assert rejected.status_code == 422
    assert "أموالاً حقيقية" in str(rejected.json())
    assert accepted.status_code == 200
    assert accepted.json()["daily_loss_enabled"] is False

    with TestClient(create_app(database_url)) as restarted:
        restored = restarted.get("/v1/account-risk/policy")
    assert restored.json()["daily_loss_enabled"] is False
    assert restored.json()["daily_loss_limit"] == "100.000000000000"


def test_global_policy_disable_requires_live_phrase_even_when_paper_is_active(
    tmp_path,
) -> None:
    database_url = f"sqlite:///{tmp_path / 'rangebot.db'}"
    payload = {
        "daily_loss_enabled": False,
        "daily_loss_limit": "100",
        "losing_trade_enabled": False,
        "losing_trade_limit": 3,
        "automatic_trade_enabled": False,
        "automatic_trade_limit": 5,
    }

    with TestClient(create_app(database_url)) as client:
        rejected = client.put("/v1/account-risk/policy", json=payload)
        accepted = client.put(
            "/v1/account-risk/policy",
            json={**payload, "confirmation": "DISABLE LIVE RISK LIMITS"},
        )

    assert rejected.status_code == 422
    assert accepted.status_code == 200
    assert accepted.json()["daily_loss_enabled"] is False
    assert accepted.json()["losing_trade_enabled"] is False
    assert accepted.json()["automatic_trade_enabled"] is False
