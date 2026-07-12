"""Minimal Arabic RTL lifecycle dashboard."""

from collections.abc import Callable

import httpx
from PySide6.QtCore import QTimer, Qt
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from rangebot.domain.runtime import RuntimeState


class RangeBotWindow(QWidget):
    """Displays fresh engine lifecycle state and retries after temporary outages."""

    def __init__(
        self,
        fetch_state: Callable[[], RuntimeState],
        refresh_interval_ms: int = 1_000,
    ) -> None:
        super().__init__()
        self._fetch_state = fetch_state
        self.is_connected = False
        self.setWindowTitle("RangeBot")
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)

        layout = QVBoxLayout(self)
        self.connection_label = QLabel("حالة الاتصال: غير متصل")
        self.lifecycle_label = QLabel("حالة المحرك: غير معروفة")
        self.heartbeat_label = QLabel("آخر نبضة: —")
        self.revision_label = QLabel("إصدار الحالة: —")
        for label in (
            self.connection_label,
            self.lifecycle_label,
            self.heartbeat_label,
            self.revision_label,
        ):
            label.setTextFormat(Qt.TextFormat.PlainText)
            label.setAlignment(Qt.AlignmentFlag.AlignRight)
            layout.addWidget(label)

        self._timer = QTimer(self)
        self._timer.setInterval(refresh_interval_ms)
        self._timer.timeout.connect(self.refresh)
        self._timer.start()
        self.refresh()

    def refresh(self) -> None:
        try:
            state = self._fetch_state()
        except httpx.HTTPError:
            self.is_connected = False
            self.connection_label.setText("حالة الاتصال: غير متصل")
            return
        self.is_connected = True
        self.connection_label.setText("حالة الاتصال: متصل")
        self.lifecycle_label.setText(f"حالة المحرك: \u2066{state.lifecycle}\u2069")
        self.heartbeat_label.setText(
            f"آخر نبضة: \u2066{state.last_heartbeat_at.isoformat()}\u2069"
        )
        self.revision_label.setText(f"إصدار الحالة: {state.state_revision}")
