"""Arabic RTL Paper watchlist widgets."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from rangebot.domain.market import PaperWatchlist


class PaperWatchlistWidget(QWidget):
    """Shows active versus monitoring-only Paper contracts in Arabic."""

    def __init__(self, watchlist: PaperWatchlist) -> None:
        super().__init__()
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        layout = QVBoxLayout(self)
        self.item_labels: list[QLabel] = []
        for item in watchlist.items:
            status = "نشط للتداول الآلي" if item.is_active else "مراقبة فقط"
            price = f" | السعر: \u2066{item.last_price}\u2069" if item.last_price else ""
            label = QLabel(f"{status}: \u2066{item.symbol}\u2069{price}")
            label.setTextFormat(Qt.TextFormat.PlainText)
            label.setAlignment(Qt.AlignmentFlag.AlignRight)
            layout.addWidget(label)
            self.item_labels.append(label)
