from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

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

    def get(self, path: str) -> dict[str, Any]:
        self.calls.append(("get", path, None))
        if path.endswith("watchlist"):
            return {"items": [{"symbol": "BTC_USDT", "direction": "both"}]}
        return {"quantity": "0", "entry_price": "0"}

    def post(self, path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        self.calls.append(("post", path, payload))
        return {}

    def delete(self, path: str) -> None:
        self.calls.append(("delete", path, None))
        return None


def test_operator_window_is_rtl_form_based_and_has_no_json_debug_surface() -> None:
    application = QApplication.instance() or QApplication([])
    client = FakeEngineClient()
    window = RangeBotWindow(client.fetch_runtime_state, refresh_interval_ms=60_000, engine_client=client)  # type: ignore[arg-type]

    assert window.layoutDirection() == Qt.LayoutDirection.RightToLeft
    assert window.tabs.count() == 7
    assert window.tabs.tabText(0) == "الرئيسية"
    assert window.tabs.tabText(3) == "دخول يدوي"
    assert "JSON" not in window.findChild(type(window.preview_summary)).text()

    window.load_watchlist()

    assert window.watchlist_table.rowCount() == 1
    assert window.watchlist_table.item(0, 0).text() == "BTC_USDT"
    window.close()
    application.quit()
