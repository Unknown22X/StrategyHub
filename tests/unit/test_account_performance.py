from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from rangebot.domain.exchange import ExchangeSnapshot
from rangebot.engine.database import apply_migrations, create_database_engine
from rangebot.engine.performance import AccountPerformanceRepository


def _snapshot(
    occurred_at: datetime,
    equity: str,
    *,
    mode: str = "live",
    error: str | None = None,
) -> ExchangeSnapshot:
    total_equity = Decimal(equity)
    return ExchangeSnapshot(
        mode=mode,
        reconciled_at=occurred_at,
        total_futures_equity=total_equity,
        total_futures_balance=total_equity,
        available_futures_balance=total_equity - Decimal("10"),
        used_margin=Decimal("10"),
        margin_usage_percentage=Decimal("10"),
        realized_pnl_total=total_equity - Decimal("100"),
        unrealized_pnl=Decimal("2"),
        fees_total=Decimal("1"),
        funding_total=Decimal("0.5"),
        net_pnl_total=total_equity - Decimal("101.5"),
        open_exposure=Decimal("30"),
        reconciliation_error=error,
    )


def test_performance_repository_deduplicates_and_calculates_drawdown(tmp_path) -> None:
    database_url = f"sqlite:///{tmp_path / 'performance.db'}"
    apply_migrations(database_url)
    repository = AccountPerformanceRepository(create_database_engine(database_url))
    now = datetime(2026, 7, 17, 10, 0, tzinfo=UTC)

    first = repository.record(_snapshot(now - timedelta(hours=3), "100"))
    duplicate = repository.record(_snapshot(now - timedelta(hours=3), "999"))
    repository.record(_snapshot(now - timedelta(hours=2), "120"))
    repository.record(_snapshot(now - timedelta(hours=1), "90"))
    repository.record(_snapshot(now, "110"))
    ignored = repository.record(_snapshot(now + timedelta(minutes=1), "500", error="offline"))

    assert first is not None
    assert duplicate is not None
    assert duplicate.point_id == first.point_id
    assert ignored is None

    series = repository.series("live", "all", now=now)
    assert [point.total_equity for point in series.points] == [
        Decimal("100"),
        Decimal("120"),
        Decimal("90"),
        Decimal("110"),
    ]
    assert series.baseline_equity == Decimal("100")
    assert series.ending_equity == Decimal("110")
    assert series.equity_change == Decimal("10")
    assert series.equity_change_percentage == Decimal("10")
    assert series.maximum_drawdown_percentage == Decimal("25")
    assert series.realized_pnl_total == Decimal("10")
    assert series.fees_total == Decimal("0")
    assert series.funding_total == Decimal("0")
    assert series.net_pnl_total == Decimal("10")


def test_today_period_uses_riyadh_midnight(tmp_path) -> None:
    database_url = f"sqlite:///{tmp_path / 'riyadh.db'}"
    apply_migrations(database_url)
    repository = AccountPerformanceRepository(create_database_engine(database_url))
    now = datetime(2026, 7, 17, 4, 0, tzinfo=UTC)  # 07:00 in Riyadh
    repository.record(_snapshot(datetime(2026, 7, 16, 20, 59, tzinfo=UTC), "90"))
    repository.record(_snapshot(datetime(2026, 7, 16, 21, 0, tzinfo=UTC), "100"))
    repository.record(_snapshot(datetime(2026, 7, 17, 3, 0, tzinfo=UTC), "105"))

    series = repository.series("live", "today", now=now)

    assert [point.total_equity for point in series.points] == [
        Decimal("100"),
        Decimal("105"),
    ]
