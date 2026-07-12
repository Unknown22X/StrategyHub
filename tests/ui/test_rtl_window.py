from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from rangebot.domain.runtime import RuntimeState
from rangebot.ui.window import RangeBotWindow


def test_arabic_rtl_window_renders_mixed_direction_status_without_mutation() -> None:
    application = QApplication.instance() or QApplication([])
    state = RuntimeState(
        lifecycle="running BTC_USDT 12.50%",
        started_at="2026-07-12T00:00:00Z",
        last_heartbeat_at="2026-07-12T00:00:01Z",
        state_revision=7,
    )
    window = RangeBotWindow(lambda: state, refresh_interval_ms=60_000)

    assert window.layoutDirection() == Qt.LayoutDirection.RightToLeft
    assert "\u2066running BTC_USDT 12.50%\u2069" in window.lifecycle_label.text()
    assert window.lifecycle_label.alignment() == Qt.AlignmentFlag.AlignRight
    assert state.state_revision == 7

    window.close()
    application.quit()
