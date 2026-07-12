"""Arabic RTL decision-details widget for Paper range analysis."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from rangebot.domain.analysis import RangeAnalysisResult


class RangeDecisionDetailsWidget(QWidget):
    """Shows each passed and failed condition without submitting any trade."""

    def __init__(self, result: RangeAnalysisResult) -> None:
        super().__init__()
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        layout = QVBoxLayout(self)
        status = "السجل جاهز" if result.history_status == "ready" else "السجل غير جاهز"
        self.history_label = QLabel(status)
        self.history_label.setTextFormat(Qt.TextFormat.PlainText)
        self.history_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        layout.addWidget(self.history_label)
        self.condition_labels: list[QLabel] = []
        for condition in result.conditions:
            status = "✓" if condition.passed else "✗"
            label = QLabel(f"{status} {condition.arabic_explanation}")
            label.setTextFormat(Qt.TextFormat.PlainText)
            label.setAlignment(Qt.AlignmentFlag.AlignRight)
            layout.addWidget(label)
            self.condition_labels.append(label)
