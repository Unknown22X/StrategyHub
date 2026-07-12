from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from rangebot.domain.analysis import ConditionDetail, RangeAnalysisResult
from rangebot.ui.range_details import RangeDecisionDetailsWidget


def test_range_details_render_arabic_condition_text() -> None:
    application = QApplication.instance() or QApplication([])
    result = RangeAnalysisResult(
        history_status="ready",
        entry_blocked=False,
        protective_actions_available=True,
        opening_price="100",
        high="120",
        low="100",
        range_percentage="20",
        long_proximity_percentage="0",
        short_proximity_percentage="16.6667",
        long_eligible=True,
        short_eligible=False,
        blocking_reasons=[],
        conditions=[
            ConditionDetail(
                name="history", passed=True, arabic_explanation="السجل جاهز"
            )
        ],
    )
    widget = RangeDecisionDetailsWidget(result)

    assert widget.layoutDirection() == Qt.LayoutDirection.RightToLeft
    assert "السجل جاهز" in widget.condition_labels[0].text()

    widget.close()
    application.quit()
