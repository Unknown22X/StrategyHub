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
            f"TP: \u2066{preview.take_profit_price}\u2069 | "
            f"SL: \u2066{preview.stop_loss_price}\u2069"
        )
        self.budget_label = QLabel(
            f"الرصيد المتاح: \u2066{preview.available_futures_balance}\u2069 | "
            f"احتياطي الأمان: \u2066{preview.safety_reserve}\u2069 | "
            f"ميزانية التخصيص: \u2066{preview.allocation_budget}\u2069"
        )
        self.entry_label = QLabel(
            f"سعر الدخول: \u2066{preview.expected_entry_price}\u2069 | "
            f"الكمية المقربة: \u2066{preview.quantity}\u2069 | "
            f"الهامش: \u2066{preview.allocated_margin}\u2069 | "
            f"القيمة الاسمية: \u2066{preview.notional_value}\u2069"
        )
        self.fees_label = QLabel(
            f"رسوم الدخول: \u2066{preview.entry_fee}\u2069 | "
            f"رسوم الخروج: \u2066{preview.estimated_exit_fee}\u2069 | "
            f"الإجمالي المطلوب: \u2066{preview.total_required}\u2069"
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
