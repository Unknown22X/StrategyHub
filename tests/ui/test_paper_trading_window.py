from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QPushButton

from rangebot.domain.runtime import RuntimeState
from rangebot.ui.window import RangeBotWindow


class FakeEngineClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, dict[str, Any] | None]] = []

    def fetch_runtime_state(self) -> RuntimeState:
        return RuntimeState(
            lifecycle="running",
            started_at="2026-07-12T00:00:00Z",
            last_heartbeat_at="2026-07-12T00:00:01Z",
            state_revision=7,
        )

    def get(self, path: str) -> Any:
        self.calls.append(("get", path, None))
        if path == "/v1/exchange/live/credentials":
            return {"mode": "live", "configured": True}
        if path.endswith("watchlist"):
            return {
                "items": [
                    {
                        "symbol": "BTC_USDT",
                        "direction": "both",
                        "last_price": "64000",
                    }
                ]
            }
        if path == "/v1/paper-account":
            return {"available_futures_balance": "1000"}
        if path.startswith("/v1/paper/contracts"):
            return [
                {
                    "symbol": "BTC_USDT",
                    "quantity_step": "0.001",
                    "minimum_quantity": "0.001",
                }
            ]
        return {"quantity": "0", "entry_price": "0"}

    def post(self, path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        self.calls.append(("post", path, payload))
        return {}

    def delete(self, path: str) -> None:
        self.calls.append(("delete", path, None))


def test_operator_window_is_rtl_form_based_and_has_no_json_debug_surface() -> None:
    application = QApplication.instance() or QApplication([])
    client = FakeEngineClient()
    window = RangeBotWindow(
        client.fetch_runtime_state, refresh_interval_ms=60_000, engine_client=client
    )  # type: ignore[arg-type]

    assert window.layoutDirection() == Qt.LayoutDirection.RightToLeft
    assert window.tabs.count() == 7
    assert window.tabs.tabText(0) == "الرئيسية"
    assert window.tabs.tabText(3) == "دخول يدوي"
    assert "JSON" not in window.preview_summary.text()

    window.load_watchlist()

    assert window.watchlist_table.rowCount() == 1
    assert window.watchlist_table.item(0, 0).text() == "BTC_USDT"
    assert window.contract_input.placeholderText() == "ابحث عن عقد مثل BTC_USDT"
    window.close()
    application.quit()


def test_add_coin_uses_symbol_route_and_immediately_refreshes_watchlist() -> None:
    application = QApplication.instance() or QApplication([])
    client = FakeEngineClient()
    window = RangeBotWindow(
        client.fetch_runtime_state,
        refresh_interval_ms=60_000,
        engine_client=client,  # type: ignore[arg-type]
    )
    window.symbol_input.setText("BTC_USDT")

    window.add_watchlist()

    assert ("post", "/v1/paper/watchlist/BTC_USDT", None) in client.calls
    assert window.watchlist_table.rowCount() == 1
    window.close()
    application.quit()


def test_saved_api_status_is_visible_after_window_reopens() -> None:
    application = QApplication.instance() or QApplication([])
    client = FakeEngineClient()

    window = RangeBotWindow(
        client.fetch_runtime_state,
        refresh_interval_ms=60_000,
        engine_client=client,  # type: ignore[arg-type]
    )

    assert "Live: محفوظة ✓" in window.api_status.text()
    assert ("get", "/v1/exchange/live/credentials", None) in client.calls
    assert window.api_key.text() == ""
    assert window.api_secret.text() == ""
    window.close()
    application.quit()


def test_typed_live_confirmation_visibly_unlocks_live_mode() -> None:
    application = QApplication.instance() or QApplication([])
    client = FakeEngineClient()
    window = RangeBotWindow(
        client.fetch_runtime_state,
        refresh_interval_ms=60_000,
        engine_client=client,  # type: ignore[arg-type]
    )
    window.live_confirmation.setText("LIVE")

    window.activate_live()

    assert ("post", "/v1/live/activate", {"confirmation": "LIVE"}) in client.calls
    assert window.mode_selector.itemText(2) == "Live — جاهز"
    assert window.live_confirmation.text() == ""
    window.close()
    application.quit()


def test_exchange_mode_ui_uses_engine_preview_and_typed_protection_controls() -> None:
    application = QApplication.instance() or QApplication([])
    client = FakeEngineClient()
    window = RangeBotWindow(
        client.fetch_runtime_state,
        refresh_interval_ms=60_000,
        engine_client=client,  # type: ignore[arg-type]
    )
    window.mode_selector.setCurrentIndex(1)
    window.create_preview()

    assert client.calls[-1][1] == "/v1/exchange/testnet/market-guard-quote"

    window.mode_selector.setCurrentIndex(2)
    window.protection_confirmation.setText("DISABLE TP")
    window.disable_live_tp()

    assert client.calls[-1][1] == "/v1/live/protection"
    assert client.calls[-1][2]["confirmation"] == "DISABLE TP"
    window.close()
    application.quit()


def test_dashboard_has_obvious_first_action_and_separate_manual_sides() -> None:
    application = QApplication.instance() or QApplication([])
    client = FakeEngineClient()
    window = RangeBotWindow(
        client.fetch_runtime_state,
        refresh_interval_ms=60_000,
        engine_client=client,  # type: ignore[arg-type]
    )

    button_labels = {button.text() for button in window.findChildren(QPushButton)}
    assert "اختر عملة للبدء" in button_labels
    assert "بدء المراقبة" in button_labels
    assert "شراء / Long" in button_labels
    assert "بيع / Short" in button_labels
    assert window.auto_toggle.text().startswith("تداول تلقائي")

    window.contract_input.setText("BTC_USDT")
    window.choose_contract()
    calls_before_monitoring = len(client.calls)
    window.start_monitoring()
    assert len(client.calls) == calls_before_monitoring

    window.create_preview()
    assert client.calls[-1][1] == "/v1/paper/entry-preview"
    assert client.calls[-1][2]["leverage"] == 5
    assert client.calls[-1][2]["take_profit_percentage"] == "10"

    window.close()
    application.quit()


def test_transport_details_are_logged_but_not_shown_to_user(caplog) -> None:
    import httpx

    class FailingClient(FakeEngineClient):
        def get(self, path: str) -> dict[str, Any]:
            raise httpx.ConnectError("http://127.0.0.1:8765/internal")

    application = QApplication.instance() or QApplication([])
    client = FailingClient()
    window = RangeBotWindow(
        client.fetch_runtime_state,
        refresh_interval_ms=60_000,
        engine_client=client,  # type: ignore[arg-type]
    )

    with caplog.at_level("WARNING"):
        window.load_watchlist()

    assert "ConnectError" in caplog.text
    assert "127.0.0.1" not in caplog.text
    assert "127.0.0.1" not in window.warning_banner.text()
    assert "المحرك غير متصل" in window.warning_banner.text()

    window.close()
    application.quit()
