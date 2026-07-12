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
        self.budget_label = QLabel(
            f"\u0627\u0644\u0631\u0635\u064a\u062f \u0627\u0644\u0645\u062a\u0627\u062d: \u2066{preview.available_futures_balance}\u2069 | "
            f"\u0627\u062d\u062a\u064a\u0627\u0637\u064a \u0627\u0644\u0623\u0645\u0627\u0646: \u2066{preview.safety_reserve}\u2069 | "
            f"\u0645\u064a\u0632\u0627\u0646\u064a\u0629 \u0627\u0644\u062a\u062e\u0635\u064a\u0635: \u2066{preview.allocation_budget}\u2069"
        )
        self.entry_label = QLabel(
            f"\u0633\u0639\u0631 \u0627\u0644\u062f\u062e\u0648\u0644: \u2066{preview.expected_entry_price}\u2069 | "
            f"\u0627\u0644\u0643\u0645\u064a\u0629 \u0627\u0644\u0645\u0642\u0631\u0628\u0629: \u2066{preview.quantity}\u2069 | "
            f"\u0627\u0644\u0647\u0627\u0645\u0634: \u2066{preview.allocated_margin}\u2069 | "
            f"\u0627\u0644\u0642\u064a\u0645\u0629 \u0627\u0644\u0627\u0633\u0645\u064a\u0629: \u2066{preview.notional_value}\u2069"
        )
        self.fees_label = QLabel(
            f"\u0631\u0633\u0648\u0645 \u0627\u0644\u062f\u062e\u0648\u0644: \u2066{preview.entry_fee}\u2069 | "
            f"\u0631\u0633\u0648\u0645 \u0627\u0644\u062e\u0631\u0648\u062c: \u2066{preview.estimated_exit_fee}\u2069 | "
            f"\u0627\u0644\u0625\u062c\u0645\u0627\u0644\u064a \u0627\u0644\u0645\u0637\u0644\u0648\u0628: \u2066{preview.total_required}\u2069"
        )
        blocks = "، ".join(preview.blocking_reasons) or "لا توجد موانع"
        self.blocking_label = QLabel(f"موانع الدخول: {blocks}")
        for label in (
            self.liquidation_label,
            self.protection_label,
            self.budget_label,
            self.entry_label,
            self.fees_label,
            self.blocking_label,
        ):
            label.setTextFormat(Qt.TextFormat.PlainText)
            label.setAlignment(Qt.AlignmentFlag.AlignRight)
            layout.addWidget(label)
