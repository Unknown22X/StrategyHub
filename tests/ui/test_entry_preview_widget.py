from decimal import Decimal

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from rangebot.domain.entry_preview import EntryPreviewRequest, create_entry_preview
from rangebot.ui.entry_preview import PaperEntryPreviewWidget


def test_entry_preview_widget_shows_paper_estimates_and_blocks() -> None:
    application = QApplication.instance() or QApplication([])
    preview = create_entry_preview(
        EntryPreviewRequest(
            available_futures_balance=Decimal("1000"),
            allocation_percentage=Decimal("100"),
            safety_reserve_percentage=Decimal("0"),
            leverage=10,
            expected_entry_price=Decimal("100"),
            quantity_step=Decimal("0.001"),
            minimum_quantity=Decimal("0.001"),
            direction="long",
            quote_revision="quote-1",
        )
    )
    widget = PaperEntryPreviewWidget(preview)

    assert widget.layoutDirection() == Qt.LayoutDirection.RightToLeft
    assert "تقدير التصفية" in widget.liquidation_label.text()
    assert "TP" in widget.protection_label.text()

    widget.close()
    application.quit()
