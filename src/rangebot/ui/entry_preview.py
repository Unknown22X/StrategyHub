"""Arabic RTL Paper Entry Preview widget."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from rangebot.domain.entry_preview import EntryPreview


class PaperEntryPreviewWidget(QWidget):
    """Displays preview values and blocks without submitting any order."""

    def __init__(self, preview: EntryPreview) -> None:
        super().__init__()
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        layout = QVBoxLayout(self)
        self.liquidation_label = QLabel(
            f"تقدير التصفية (Paper): \u2066{preview.estimated_liquidation_price}\u2069"
        )
        self.protection_label = QLabel(
            f"TP: \u2066{preview.take_profit_price}\u2069 | SL: \u2066{preview.stop_loss_price}\u2069"
        )
        blocks = "، ".join(preview.blocking_reasons) or "لا توجد موانع"
        self.blocking_label = QLabel(f"موانع الدخول: {blocks}")
        for label in (self.liquidation_label, self.protection_label, self.blocking_label):
            label.setTextFormat(Qt.TextFormat.PlainText)
            label.setAlignment(Qt.AlignmentFlag.AlignRight)
            layout.addWidget(label)
