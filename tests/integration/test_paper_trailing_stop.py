from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from rangebot.domain.exchange import ExchangeEntryRequest
from rangebot.domain.paper import PaperProtectionCheck
from rangebot.engine.api import create_app


def _open_trailing_position(app, *, direction: str) -> None:
    repository = app.state.paper_repository
    request = ExchangeEntryRequest(
        symbol="BTC_USDT",
        direction=direction,
        order_type="market",
        quantity=Decimal("1"),
        client_request_id=f"trail-{direction}",
        leverage=5,
        take_profit_price=Decimal("130") if direction == "long" else Decimal("70"),
        stop_loss_price=Decimal("90") if direction == "long" else Decimal("110"),
        trailing_stop_price=Decimal("95") if direction == "long" else Decimal("105"),
        trailing_stop_distance=Decimal("5"),
        origin="automatic_strategy",
    )
    repository.enter_central_market(
        request,
        fill_price=Decimal("100"),
        contract_multiplier=Decimal("1"),
    )


def test_paper_long_trailing_stop_ratchets_survives_restart_and_triggers(tmp_path) -> None:
    database_url = f"sqlite:///{tmp_path / 'rangebot.db'}"
    app = create_app(database_url)
    with TestClient(app) as client:
        client.post(
            "/v1/paper-account/initialize",
            json={"starting_balance": "1000", "reason": "long trail"},
        )
        _open_trailing_position(app, direction="long")
        first = app.state.paper_repository.check_protection(
            PaperProtectionCheck(market_price=Decimal("110"))
        )
        protection = app.state.paper_repository.protection()
        lower_market = app.state.paper_repository.check_protection(
            PaperProtectionCheck(market_price=Decimal("108"))
        )
        unchanged = app.state.paper_repository.protection()

    assert first.triggered is False
    assert protection.trailing_extremum_price == Decimal("110")
    assert protection.trailing_stop_price == Decimal("105")
    assert lower_market.triggered is False
    assert unchanged.trailing_extremum_price == Decimal("110")
    assert unchanged.trailing_stop_price == Decimal("105")

    restarted = create_app(database_url)
    with TestClient(restarted):
        restored = restarted.state.paper_repository.protection()
        triggered = restarted.state.paper_repository.check_protection(
            PaperProtectionCheck(market_price=Decimal("104"))
        )
        with pytest.raises(LookupError):
            restarted.state.paper_repository.protection()
        with pytest.raises(LookupError):
            restarted.state.paper_repository.position()

    assert restored.trailing_stop_price == Decimal("105")
    assert restored.trailing_distance == Decimal("5")
    assert triggered.triggered is True
    assert triggered.reason == "trailing_stop"
    assert "وقف التتبع" in (triggered.activity or "")


def test_paper_short_trailing_stop_ratchets_down_and_triggers(tmp_path) -> None:
    app = create_app(f"sqlite:///{tmp_path / 'rangebot.db'}")
    with TestClient(app) as client:
        client.post(
            "/v1/paper-account/initialize",
            json={"starting_balance": "1000", "reason": "short trail"},
        )
        _open_trailing_position(app, direction="short")
        first = app.state.paper_repository.check_protection(
            PaperProtectionCheck(market_price=Decimal("90"))
        )
        protection = app.state.paper_repository.protection()
        triggered = app.state.paper_repository.check_protection(
            PaperProtectionCheck(market_price=Decimal("96"))
        )

    assert first.triggered is False
    assert protection.trailing_extremum_price == Decimal("90")
    assert protection.trailing_stop_price == Decimal("95")
    assert triggered.triggered is True
    assert triggered.reason == "trailing_stop"


def test_paper_emergency_stop_preserves_active_trailing_protection(tmp_path) -> None:
    app = create_app(f"sqlite:///{tmp_path / 'rangebot.db'}")
    with TestClient(app) as client:
        client.post(
            "/v1/paper-account/initialize",
            json={"starting_balance": "1000", "reason": "emergency trail"},
        )
        _open_trailing_position(app, direction="long")
        app.state.paper_repository.check_protection(
            PaperProtectionCheck(market_price=Decimal("110"))
        )
        stopped = client.post(
            "/v1/paper/emergency-stop",
            json={"confirmation": "EMERGENCY STOP", "reason": "operator request"},
        )
        preserved = app.state.paper_repository.protection()
        position = app.state.paper_repository.position()
        triggered = app.state.paper_repository.check_protection(
            PaperProtectionCheck(market_price=Decimal("104"))
        )

    assert stopped.status_code == 200
    assert stopped.json()["active"] is True
    assert preserved.trailing_stop_price == Decimal("105")
    assert preserved.trailing_distance == Decimal("5")
    assert position.quantity == Decimal("1")
    assert triggered.triggered is True
    assert triggered.reason == "trailing_stop"
