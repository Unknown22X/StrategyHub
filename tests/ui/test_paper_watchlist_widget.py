from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from rangebot.domain.market import PaperWatchlist, WatchlistItem
from rangebot.ui.paper_dashboard import PaperWatchlistWidget


def test_paper_watchlist_renders_arabic_status_with_latin_symbol() -> None:
    application = QApplication.instance() or QApplication([])
    widget = PaperWatchlistWidget(
        PaperWatchlist(
            items=[
                WatchlistItem(
                    symbol="BTC_USDT",
                    priority=1,
                    is_active=False,
                    monitoring_only=True,
                )
            ],
            automatic_trading_enabled=False,
        )
    )

    assert widget.layoutDirection() == Qt.LayoutDirection.RightToLeft
    assert "BTC_USDT" in widget.item_labels[0].text()
    assert "مراقبة فقط" in widget.item_labels[0].text()

    widget.close()
    application.quit()
