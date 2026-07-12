"""Functional Arabic RTL desktop controls for local Paper Trading."""

import json
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
from PySide6.QtCore import QTimer, Qt
from PySide6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from rangebot.domain.runtime import RuntimeState
from rangebot.ui.client import EngineClient


DEFAULT_ENTRY = {
    "available_futures_balance": "1000",
    "allocation_percentage": "25",
    "safety_reserve_percentage": "10",
    "leverage": 5,
    "expected_entry_price": "100",
    "quantity_step": "0.001",
    "minimum_quantity": "0.001",
    "taker_fee_rate": "0.001",
    "direction": "long",
    "quote_revision": "manual-1",
}


class RangeBotWindow(QWidget):
    """Runs local Paper operations with Arabic RTL labels and safe confirmations."""

    def __init__(
        self,
        fetch_state: Callable[[], RuntimeState],
        refresh_interval_ms: int = 1_000,
        engine_client: EngineClient | None = None,
    ) -> None:
        super().__init__()
        self._fetch_state = fetch_state
        self._client = engine_client
        self._last_preview: dict[str, Any] | None = None
        self.is_connected = False
        self.setWindowTitle("RangeBot Paper Trading")
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self.resize(1120, 780)

        root = QVBoxLayout(self)
        root.addLayout(self._build_status_bar())
        self.tabs = QTabWidget()
        self.tabs.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self.tabs.addTab(self._account_tab(), "حساب Paper")
        self.tabs.addTab(self._watchlist_tab(), "قائمة المراقبة")
        self.tabs.addTab(self._analysis_tab(), "تحليل النطاق")
        self.tabs.addTab(self._entry_tab(), "الدخول والمعاينة")
        self.tabs.addTab(self._position_tab(), "المركز والحماية")
        self.tabs.addTab(self._operations_tab(), "المخاطر والطوارئ")
        self.tabs.addTab(self._operator_tab(), "الملفات والسجل والمساعدة")
        root.addWidget(self.tabs)

        self._timer = QTimer(self)
        self._timer.setInterval(refresh_interval_ms)
        self._timer.timeout.connect(self.refresh)
        self._timer.start()
        self.refresh()

    def _build_status_bar(self) -> QHBoxLayout:
        layout = QHBoxLayout()
        self.connection_label = QLabel("حالة الاتصال: غير متصل")
        self.lifecycle_label = QLabel("حالة المحرك: غير معروفة")
        self.heartbeat_label = QLabel("آخر نبضة: —")
        self.revision_label = QLabel("إصدار الحالة: —")
        refresh_button = QPushButton("تحديث")
        refresh_button.clicked.connect(self.refresh_all)
        for label in (
            self.connection_label,
            self.lifecycle_label,
            self.heartbeat_label,
            self.revision_label,
        ):
            label.setTextFormat(Qt.TextFormat.PlainText)
            label.setAlignment(Qt.AlignmentFlag.AlignRight)
            layout.addWidget(label)
        layout.addWidget(refresh_button)
        return layout

    def _account_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        form = QFormLayout()
        self.account_balance = QLineEdit("1000")
        self.account_reason = QLineEdit("إعداد حساب Paper")
        form.addRow("الرصيد الابتدائي", self.account_balance)
        form.addRow("سبب العملية", self.account_reason)
        layout.addLayout(form)
        buttons = QHBoxLayout()
        initialize = QPushButton("تهيئة الحساب")
        initialize.clicked.connect(self.initialize_account)
        reset = QPushButton("إعادة ضبط الحساب")
        reset.clicked.connect(self.reset_account)
        buttons.addWidget(initialize)
        buttons.addWidget(reset)
        layout.addLayout(buttons)
        self.account_output = self._output_box()
        layout.addWidget(self.account_output)
        return tab

    def _watchlist_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        form = QFormLayout()
        self.symbol_input = QLineEdit("BTC_USDT")
        form.addRow("العقد", self.symbol_input)
        layout.addLayout(form)
        buttons = QGridLayout()
        for column, (label, handler) in enumerate(
            (
                ("إضافة", self.add_watchlist),
                ("تعيين نشط", self.activate_watchlist),
                ("بدء التلقائي", self.start_automation),
                ("تحديث القائمة", self.load_watchlist),
            )
        ):
            button = QPushButton(label)
            button.clicked.connect(handler)
            buttons.addWidget(button, 0, column)
        layout.addLayout(buttons)
        self.watchlist_output = self._output_box()
        layout.addWidget(self.watchlist_output)
        return tab

    def _analysis_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.addWidget(QLabel("أدخل طلب تحليل النطاق بصيغة JSON. يعرض الناتج الإشارات وأسباب منع الدخول."))
        self.analysis_input = self._json_box(
            {
                "config": {
                    "timeframe_minutes": 5,
                    "range_mode": "interval",
                    "minimum_range_percentage": "20",
                    "maximum_range_percentage": "25",
                },
                "candles": [],
                "last_price": "100",
                "symbol": "BTC_USDT",
            }
        )
        button = QPushButton("تحليل النطاق")
        button.clicked.connect(self.evaluate_analysis)
        self.analysis_output = self._output_box()
        layout.addWidget(self.analysis_input)
        layout.addWidget(button)
        layout.addWidget(self.analysis_output)
        return tab

    def _entry_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        entry_group = QGroupBox("مدخلات معاينة الدخول")
        entry_layout = QVBoxLayout(entry_group)
        self.entry_input = self._json_box(DEFAULT_ENTRY)
        entry_layout.addWidget(self.entry_input)
        preview_button = QPushButton("إنشاء معاينة Paper")
        preview_button.clicked.connect(self.create_preview)
        entry_layout.addWidget(preview_button)
        layout.addWidget(entry_group)

        actions = QGroupBox("أوامر الدخول")
        action_layout = QFormLayout(actions)
        self.entry_direction = QComboBox()
        self.entry_direction.addItem("شراء / Long", "long")
        self.entry_direction.addItem("بيع / Short", "short")
        self.limit_price = QLineEdit("99")
        self.placement_price = QLineEdit("100")
        action_layout.addRow("الاتجاه", self.entry_direction)
        action_layout.addRow("سعر Limit", self.limit_price)
        action_layout.addRow("سعر السوق عند الإدخال", self.placement_price)
        market = QPushButton("تنفيذ Market بعد التأكيد")
        market.clicked.connect(self.submit_market_entry)
        limit = QPushButton("إنشاء Limit بعد التأكيد")
        limit.clicked.connect(self.submit_limit_entry)
        action_layout.addRow(market, limit)
        layout.addWidget(actions)
        self.preview_output = self._output_box()
        layout.addWidget(self.preview_output)
        return tab

    def _position_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        form = QFormLayout()
        self.exit_price = QLineEdit("100")
        form.addRow("سعر الإغلاق/الفحص", self.exit_price)
        layout.addLayout(form)
        actions = QGridLayout()
        for column, (label, handler) in enumerate(
            (
                ("تحديث المركز", self.load_position),
                ("فحص TP/SL", self.check_protection),
                ("إغلاق المركز", self.close_position),
                ("إلغاء Limit", self.cancel_pending),
                ("إغلاق طارئ", self.emergency_close),
            )
        ):
            button = QPushButton(label)
            button.clicked.connect(handler)
            actions.addWidget(button, 0, column)
        layout.addLayout(actions)
        self.position_output = self._output_box()
        layout.addWidget(self.position_output)
        return tab

    def _operations_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.addWidget(QLabel("إعدادات المخاطر اليومية والتهدئة"))
        self.risk_input = self._json_box(
            {
                "daily_loss_limit": "100",
                "losing_trade_limit": 3,
                "automatic_fill_limit": 10,
                "cooldown_seconds": 60,
            }
        )
        risk_buttons = QHBoxLayout()
        get_risk = QPushButton("عرض المخاطر")
        get_risk.clicked.connect(self.load_risk)
        save_risk = QPushButton("حفظ إعدادات المخاطر")
        save_risk.clicked.connect(self.save_risk)
        stop = QPushButton("إيقاف طارئ")
        stop.clicked.connect(self.emergency_stop)
        resume = QPushButton("استئناف RESUME")
        resume.clicked.connect(self.resume_emergency)
        for button in (get_risk, save_risk, stop, resume):
            risk_buttons.addWidget(button)
        layout.addWidget(self.risk_input)
        layout.addLayout(risk_buttons)
        self.risk_output = self._output_box()
        layout.addWidget(self.risk_output)
        return tab

    def _operator_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        self.profile_input = self._json_box(
            {"name": "محافظ", "settings": {"leverage": 5, "theme": "dark"}}
        )
        self.profile_id = QLineEdit("1")
        profile_buttons = QHBoxLayout()
        save = QPushButton("حفظ ملف")
        save.clicked.connect(self.save_profile)
        profiles = QPushButton("عرض الملفات")
        profiles.clicked.connect(self.load_profiles)
        apply = QPushButton("تطبيق الملف")
        apply.clicked.connect(self.apply_profile)
        update = QPushButton("تعديل الملف")
        update.clicked.connect(self.update_profile)
        duplicate = QPushButton("نسخ الملف")
        duplicate.clicked.connect(self.duplicate_profile)
        delete = QPushButton("حذف الملف")
        delete.clicked.connect(self.delete_profile)
        audit = QPushButton("السجل العربي")
        audit.clicked.connect(self.load_audit)
        help_button = QPushButton("مركز المساعدة")
        help_button.clicked.connect(self.load_help)
        verify = QPushButton("تسجيل تحقق Paper")
        verify.clicked.connect(self.record_verification)
        status = QPushButton("حالة التحقق")
        status.clicked.connect(self.load_verification)
        for button in (
            save,
            profiles,
            apply,
            update,
            duplicate,
            delete,
            audit,
            help_button,
            verify,
            status,
        ):
            profile_buttons.addWidget(button)
        layout.addWidget(QLabel("الملفات المحفوظة والسجل والمساعدة والتحقق"))
        profile_form = QFormLayout()
        profile_form.addRow("رقم الملف", self.profile_id)
        layout.addLayout(profile_form)
        layout.addWidget(self.profile_input)
        layout.addLayout(profile_buttons)
        self.operator_output = self._output_box()
        layout.addWidget(self.operator_output)
        return tab

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
        self.revision_label.setText(f"إصدار الحالة: \u2066{state.state_revision}\u2069")

    def refresh_all(self) -> None:
        self.refresh()
        if self._client is None:
            return
        self.load_account()
        self.load_watchlist()
        self.load_position()
        self.load_risk()

    def initialize_account(self) -> None:
        self._call(
            self.account_output,
            "post",
            "/v1/paper-account/initialize",
            {
                "starting_balance": self.account_balance.text(),
                "reason": self.account_reason.text(),
            },
        )

    def reset_account(self) -> None:
        self._call(
            self.account_output,
            "post",
            "/v1/paper-account/reset",
            {
                "starting_balance": self.account_balance.text(),
                "reason": self.account_reason.text(),
                "confirmation": "RESET PAPER ACCOUNT",
            },
        )

    def load_account(self) -> None:
        self._call(self.account_output, "get", "/v1/paper-account")

    def add_watchlist(self) -> None:
        self._call(self.watchlist_output, "post", f"/v1/paper/watchlist/{self.symbol_input.text()}")

    def activate_watchlist(self) -> None:
        self._call(self.watchlist_output, "post", f"/v1/paper/watchlist/{self.symbol_input.text()}/active")

    def start_automation(self) -> None:
        self._call(self.watchlist_output, "post", "/v1/paper/automatic-trading/start")

    def load_watchlist(self) -> None:
        self._call(self.watchlist_output, "get", "/v1/paper/watchlist")

    def evaluate_analysis(self) -> None:
        self._call(self.analysis_output, "post", "/v1/paper/range-analysis/evaluate", self._json(self.analysis_input))

    def create_preview(self) -> None:
        payload = self._entry_payload()
        result = self._call(self.preview_output, "post", "/v1/paper/entry-preview", payload)
        if isinstance(result, dict):
            self._last_preview = result

    def submit_market_entry(self) -> None:
        request = self._entry_payload()
        preview = self._ensure_preview(request)
        if preview is None:
            return
        self._call(
            self.preview_output,
            "post",
            "/v1/paper/market-entry",
            {
                "preview": preview,
                "current_request": request,
                "confirmation": "CONFIRM PAPER MARKET ENTRY",
            },
        )

    def submit_limit_entry(self) -> None:
        request = self._entry_payload()
        preview = self._ensure_preview(request)
        if preview is None:
            return
        self._call(
            self.preview_output,
            "post",
            "/v1/paper/limit-entry",
            {
                "preview": preview,
                "current_request": request,
                "limit_price": self.limit_price.text(),
                "placement_price": self.placement_price.text(),
                "expires_at": (datetime.now(UTC) + timedelta(seconds=60)).isoformat(),
                "confirmation": "CONFIRM PAPER LIMIT ENTRY",
            },
        )

    def load_position(self) -> None:
        self._call(self.position_output, "get", "/v1/paper/position")

    def check_protection(self) -> None:
        self._call(self.position_output, "post", "/v1/paper/position/protection/check", {"market_price": self.exit_price.text()})

    def close_position(self) -> None:
        self._call(self.position_output, "post", "/v1/paper/position/close", {"market_price": self.exit_price.text(), "confirmation": "CLOSE PAPER POSITION"})

    def cancel_pending(self) -> None:
        self._call(self.position_output, "delete", "/v1/paper/pending-entry")

    def emergency_close(self) -> None:
        self._call(self.position_output, "post", "/v1/paper/emergency-close", {"market_price": self.exit_price.text(), "confirmation": "EMERGENCY CLOSE PAPER POSITION"})

    def load_risk(self) -> None:
        self._call(self.risk_output, "get", "/v1/paper/risk")

    def save_risk(self) -> None:
        self._call(self.risk_output, "put", "/v1/paper/risk/settings", self._json(self.risk_input))

    def emergency_stop(self) -> None:
        self._call(self.risk_output, "post", "/v1/paper/emergency-stop", {"confirmation": "EMERGENCY STOP", "reason": "طلب المشغل من الواجهة"})

    def resume_emergency(self) -> None:
        self._call(self.risk_output, "post", "/v1/paper/emergency-stop/resume", {"confirmation": "RESUME"})

    def save_profile(self) -> None:
        self._call(self.operator_output, "post", "/v1/paper/profiles", self._json(self.profile_input))

    def load_profiles(self) -> None:
        self._call(self.operator_output, "get", "/v1/paper/profiles")

    def apply_profile(self) -> None:
        payload = self._json(self.profile_input)
        payload["confirmation"] = "APPLY PAPER PROFILE"
        self._call(
            self.operator_output,
            "post",
            f"/v1/paper/profiles/{self.profile_id.text()}/apply",
            payload,
        )

    def update_profile(self) -> None:
        self._call(
            self.operator_output,
            "put",
            f"/v1/paper/profiles/{self.profile_id.text()}",
            self._json(self.profile_input),
        )

    def duplicate_profile(self) -> None:
        self._call(
            self.operator_output,
            "post",
            f"/v1/paper/profiles/{self.profile_id.text()}/duplicate",
            self._json(self.profile_input),
        )

    def delete_profile(self) -> None:
        self._call(
            self.operator_output,
            "delete",
            f"/v1/paper/profiles/{self.profile_id.text()}",
        )

    def load_audit(self) -> None:
        self._call(self.operator_output, "get", "/v1/paper-account/audit")

    def load_help(self) -> None:
        self._call(self.operator_output, "get", "/v1/paper/help")

    def record_verification(self) -> None:
        self._call(self.operator_output, "post", "/v1/paper/verification", {"evidence": "مراجعة يدوية من واجهة Paper"})

    def load_verification(self) -> None:
        self._call(self.operator_output, "get", "/v1/paper/verification")

    def _entry_payload(self) -> dict[str, Any]:
        payload = self._json(self.entry_input)
        payload["direction"] = self.entry_direction.currentData()
        return payload

    def _ensure_preview(self, request: dict[str, Any]) -> dict[str, Any] | None:
        if self._last_preview is not None:
            return self._last_preview
        result = self._call(self.preview_output, "post", "/v1/paper/entry-preview", request)
        if isinstance(result, dict):
            self._last_preview = result
            return result
        return None

    def _call(
        self,
        output: QPlainTextEdit,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
    ) -> Any:
        if self._client is None:
            output.setPlainText("واجهة الاختبار لا تملك عميلا للمحرك.")
            return None
        try:
            result = getattr(self._client, method)(path, payload) if payload is not None else getattr(self._client, method)(path)
        except (httpx.HTTPError, ValueError, json.JSONDecodeError) as error:
            output.setPlainText(f"خطأ: {error}")
            return None
        output.setPlainText(json.dumps(result, ensure_ascii=False, indent=2, default=str))
        return result

    @staticmethod
    def _json(widget: QPlainTextEdit) -> dict[str, Any]:
        return json.loads(widget.toPlainText())

    @staticmethod
    def _json_box(value: dict[str, Any]) -> QPlainTextEdit:
        box = QPlainTextEdit(json.dumps(value, ensure_ascii=False, indent=2))
        box.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        box.setMinimumHeight(130)
        return box

    @staticmethod
    def _output_box() -> QPlainTextEdit:
        box = QPlainTextEdit()
        box.setReadOnly(True)
        box.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        box.setMinimumHeight(150)
        return box
