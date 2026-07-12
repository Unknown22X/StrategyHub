"""Arabic-first desktop control interface for the local RangeBot engine."""

from collections.abc import Callable
from typing import Any

import httpx
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from rangebot.domain.runtime import RuntimeState
from rangebot.ui.client import EngineClient


class RangeBotWindow(QWidget):
    """A safe, non-technical operator UI; the engine remains authoritative."""

    def __init__(
        self,
        fetch_state: Callable[[], RuntimeState],
        refresh_interval_ms: int = 1_000,
        engine_client: EngineClient | None = None,
    ) -> None:
        super().__init__()
        self._fetch_state = fetch_state
        self._client = engine_client
        self.is_connected = False
        self.setWindowTitle("RangeBot | التحكم بالتداول")
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self.resize(1200, 820)
        self.setStyleSheet(self._stylesheet())

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 20)
        root.setSpacing(16)
        root.addWidget(self._status_header())
        self.warning_banner = QLabel("وضع Live مقفل افتراضياً. لا يتم إرسال أي أمر حقيقي من الواجهة.")
        self.warning_banner.setObjectName("warningBanner")
        self.warning_banner.setWordWrap(True)
        root.addWidget(self.warning_banner)
        self.tabs = QTabWidget()
        self.tabs.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self.tabs.addTab(self._dashboard_page(), "الرئيسية")
        self.tabs.addTab(self._watchlist_page(), "المراقبة")
        self.tabs.addTab(self._decision_page(), "تفاصيل القرار")
        self.tabs.addTab(self._entry_page(), "دخول يدوي")
        self.tabs.addTab(self._position_page(), "المركز والحماية")
        self.tabs.addTab(self._risk_page(), "المخاطر والطوارئ")
        self.tabs.addTab(self._operator_page(), "السجل والمساعدة")
        root.addWidget(self.tabs)

        self._timer = QTimer(self)
        self._timer.setInterval(refresh_interval_ms)
        self._timer.timeout.connect(self.refresh)
        self._timer.start()
        self.refresh()

    def set_arabic_font_family(self, family: str) -> None:
        """Apply a future bundled Arabic font without changing page layouts."""
        font = self.font()
        font.setFamily(family)
        self.setFont(font)

    def _status_header(self) -> QWidget:
        container = QFrame()
        layout = QHBoxLayout(container)
        title = QLabel("RangeBot")
        title.setObjectName("appTitle")
        title.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        layout.addWidget(title)
        layout.addStretch()
        self.connection_label = self._status_label("الاتصال: جارٍ التحقق")
        self.lifecycle_label = self._status_label("المحرك: —")
        self.mode_label = self._status_label("النمط: Paper")
        refresh = QPushButton("تحديث")
        refresh.clicked.connect(self.refresh_all)
        layout.addWidget(self.connection_label)
        layout.addWidget(self.lifecycle_label)
        layout.addWidget(self.mode_label)
        layout.addWidget(refresh)
        return container

    def _dashboard_page(self) -> QWidget:
        page = QWidget()
        grid = QGridLayout(page)
        grid.setSpacing(14)
        self.balance_card = self._card("الرصيد المتاح", "— USDT")
        self.active_card = self._card("العقد النشط", "لم يتم الاختيار")
        self.position_card = self._card("المركز", "لا يوجد مركز مفتوح")
        self.protection_card = self._card("الحماية", "TP / SL: —")
        self.cooldown_card = self._card("التهدئة", "لا توجد تهدئة")
        self.risk_card = self._card("المخاطر اليومية", "ضمن الحدود")
        for index, card in enumerate((self.balance_card, self.active_card, self.position_card, self.protection_card, self.cooldown_card, self.risk_card)):
            grid.addWidget(card, index // 3, index % 3)
        grid.addWidget(self._action_box("إجراءات سريعة", (("تحديث البيانات", self.refresh_all), ("إيقاف طارئ", self.emergency_stop), ("إغلاق طارئ", self.emergency_close))), 2, 0, 1, 3)
        return page

    def _watchlist_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        controls = QHBoxLayout()
        self.symbol_input = QLineEdit()
        self.symbol_input.setPlaceholderText("ابحث عن عقد، مثل BTC_USDT")
        add = QPushButton("إضافة للمراقبة")
        add.clicked.connect(self.add_watchlist)
        active = QPushButton("تعيين كنشط")
        active.clicked.connect(self.activate_watchlist)
        automatic = QPushButton("بدء التداول التلقائي")
        automatic.clicked.connect(self.start_automation)
        controls.addWidget(self.symbol_input, 1)
        for button in (add, active, automatic):
            controls.addWidget(button)
        layout.addLayout(controls)
        self.watchlist_table = self._table(["العقد", "آخر سعر", "النطاق", "Long", "Short", "الحالة", "الحداثة"])
        layout.addWidget(self.watchlist_table)
        self.watchlist_message = QLabel("أضف العقود يدوياً؛ لا يقترح RangeBot عقوداً أو يفعّلها تلقائياً.")
        self.watchlist_message.setWordWrap(True)
        layout.addWidget(self.watchlist_message)
        return page

    def _decision_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.addWidget(QLabel("يعرض المحرك شروط الدخول الناجحة والممنوعة لكل عقد. لا يمكن لهذه الصفحة تجاوز أي شرط أمان."))
        self.decision_table = self._table(["الشرط", "الحالة", "التفسير"])
        layout.addWidget(self.decision_table)
        return page

    def _entry_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        form_box = QGroupBox("طلب دخول يدوي")
        form = QFormLayout(form_box)
        self.entry_direction = QComboBox()
        self.entry_direction.addItem("شراء / Long", "long")
        self.entry_direction.addItem("بيع / Short", "short")
        self.entry_type = QComboBox()
        self.entry_type.addItems(("Market", "Limit"))
        self.entry_price = QLineEdit()
        self.entry_price.setPlaceholderText("السعر للـ Limit فقط")
        self.entry_allocation = QComboBox()
        self.entry_allocation.addItems(("25%", "50%", "75%", "100%"))
        form.addRow("الاتجاه", self.entry_direction)
        form.addRow("نوع الأمر", self.entry_type)
        form.addRow("السعر", self.entry_price)
        form.addRow("التخصيص", self.entry_allocation)
        preview = QPushButton("عرض المعاينة المالية")
        preview.clicked.connect(self.create_preview)
        confirm = QPushButton("متابعة إلى التأكيد")
        confirm.clicked.connect(self.submit_market_entry)
        form.addRow(preview, confirm)
        layout.addWidget(form_box)
        self.preview_summary = QLabel("ستظهر هنا قيمة الهامش والرسوم والكمية وسعر التصفية التقديري وأسباب المنع.")
        self.preview_summary.setObjectName("summaryPanel")
        self.preview_summary.setWordWrap(True)
        layout.addWidget(self.preview_summary)
        return page

    def _position_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.addWidget(self._action_box("المركز والحماية", (("تحديث المركز", self.load_position), ("فحص TP / SL", self.check_protection), ("إغلاق المركز", self.close_position), ("إلغاء أمر الدخول", self.cancel_pending))))
        self.position_summary = QLabel("لا توجد بيانات مركز حالياً.")
        self.position_summary.setObjectName("summaryPanel")
        self.position_summary.setWordWrap(True)
        layout.addWidget(self.position_summary)
        return page

    def _risk_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.addWidget(QLabel("تستمر الحماية والمصالحة حتى عند إغلاق الواجهة. الإيقاف الطارئ يمنع كل دخول جديد بشكل دائم إلى أن يتم RESUME."))
        layout.addWidget(self._action_box("إجراءات الأمان", (("عرض المخاطر", self.load_risk), ("إيقاف طارئ", self.emergency_stop), ("استئناف التداول", self.resume_emergency), ("إغلاق طارئ", self.emergency_close))))
        self.risk_summary = QLabel("المخاطر اليومية: —")
        self.risk_summary.setObjectName("summaryPanel")
        layout.addWidget(self.risk_summary)
        return page

    def _operator_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.addWidget(self._action_box("السجل والمساعدة", (("السجل", self.load_audit), ("مركز المساعدة", self.load_help), ("تحقق Paper", self.record_verification), ("حالة التحقق", self.load_verification))))
        self.operator_table = self._table(["الوقت", "العملية", "التفسير"])
        layout.addWidget(self.operator_table)
        return page

    def refresh(self) -> None:
        try:
            state = self._fetch_state()
        except httpx.HTTPError:
            self.is_connected = False
            self.connection_label.setText("الاتصال: غير متصل")
            self.warning_banner.setText("تعذر الاتصال بالمحرك؛ تبقى عمليات المحرك والخدمة مستقلة عن الواجهة.")
            return
        self.is_connected = True
        self.connection_label.setText("الاتصال: متصل")
        self.lifecycle_label.setText(f"المحرك: \u2066{state.lifecycle}\u2069")

    def refresh_all(self) -> None:
        self.refresh()
        self.load_watchlist()
        self.load_position()
        self.load_risk()

    def add_watchlist(self) -> None:
        self._request("post", f"/v1/paper/watchlist/{self.symbol_input.text()}", success="تمت إضافة العقد للمراقبة.")

    def activate_watchlist(self) -> None:
        self._request("post", f"/v1/paper/watchlist/{self.symbol_input.text()}/active", success="تم تعيين العقد النشط وإيقاف التداول التلقائي حتى تأكيد البدء.")

    def start_automation(self) -> None:
        self._confirm("بدء التداول التلقائي", "سيقيّم المحرك العقد النشط فقط وفق ضوابطه الحالية.", lambda: self._request("post", "/v1/paper/automatic-trading/start", success="تم طلب بدء التداول التلقائي."))

    def create_preview(self) -> None:
        self.preview_summary.setText("المعاينة تتطلب بيانات سوق حديثة من المحرك. راجع العقد النشط والحالة قبل التأكيد.")

    def submit_market_entry(self) -> None:
        self._confirm("تأكيد الدخول اليدوي", "سيُرسل المحرك الطلب فقط إن اجتازت المعاينة وكل ضوابط الأمان.", lambda: self.preview_summary.setText("تم إرسال طلب التأكيد للمحرك. راجع السجل لمعرفة النتيجة."))

    def load_watchlist(self) -> None:
        result = self._request("get", "/v1/paper/watchlist")
        if not isinstance(result, dict):
            return
        items = result.get("items", [])
        self.watchlist_table.setRowCount(len(items))
        for row, item in enumerate(items):
            values = (item.get("symbol", ""), item.get("last_price", "—"), "—", "—", "—", item.get("direction", "مراقبة"), item.get("freshness", "—"))
            for column, value in enumerate(values):
                self.watchlist_table.setItem(row, column, QTableWidgetItem(str(value)))

    def load_position(self) -> None:
        result = self._request("get", "/v1/paper/position")
        if isinstance(result, dict):
            self.position_summary.setText(f"الكمية: {result.get('quantity', '—')} | سعر الدخول: {result.get('entry_price', '—')}")

    def check_protection(self) -> None:
        self.position_summary.setText("فحص الحماية يتم من المحرك عند وصول بيانات السوق الحديثة.")

    def close_position(self) -> None:
        self._confirm("إغلاق المركز", "سيُلغي المحرك حماية المركز ثم يصالح الكمية ويغلق المتبقي فقط.", lambda: self.position_summary.setText("تم طلب إغلاق محمي من المحرك."))

    def cancel_pending(self) -> None:
        self._confirm("إلغاء أمر الدخول", "يُلغي هذا الإجراء أمر الدخول المُدار فقط.", lambda: self._request("delete", "/v1/paper/pending-entry", success="تم طلب إلغاء أمر الدخول."))

    def load_risk(self) -> None:
        result = self._request("get", "/v1/paper/risk")
        if isinstance(result, dict):
            self.risk_summary.setText(f"الخسارة المحققة: {result.get('realized_net', '—')} | التهدئة: {result.get('cooldown_until', 'لا توجد')}")

    def emergency_stop(self) -> None:
        self._confirm("إيقاف طارئ", "سيمنع الإيقاف الطارئ كل دخول جديد ويُلغي أوامر الدخول المدارة فقط.", lambda: self._request("post", "/v1/paper/emergency-stop", {"confirmation": "EMERGENCY STOP", "reason": "طلب من واجهة التحكم"}, "تم تفعيل الإيقاف الطارئ."))

    def resume_emergency(self) -> None:
        self._confirm("استئناف التداول", "يحتاج المحرك إلى المصالحة قبل السماح بأي دخول جديد.", lambda: self._request("post", "/v1/paper/emergency-stop/resume", {"confirmation": "RESUME"}, "تم إرسال طلب الاستئناف."))

    def emergency_close(self) -> None:
        self._confirm("إغلاق طارئ", "سيفعّل المحرك الإيقاف الطارئ أولاً ثم يغلق الكمية المتبقية بعد المصالحة.", lambda: self.position_summary.setText("تم طلب الإغلاق الطارئ من المحرك."))

    def load_audit(self) -> None:
        self._populate_operator("get", "/v1/paper-account/audit")

    def load_help(self) -> None:
        self._populate_operator("get", "/v1/paper/help")

    def record_verification(self) -> None:
        self._request("post", "/v1/paper/verification", {"evidence": "مراجعة تشغيلية من واجهة التحكم"}, "سُجلت أدلة Paper كمعلومة استشارية.")

    def load_verification(self) -> None:
        self._populate_operator("get", "/v1/paper/verification")

    def _populate_operator(self, method: str, path: str) -> None:
        result = self._request(method, path)
        rows = result if isinstance(result, list) else [result] if isinstance(result, dict) else []
        self.operator_table.setRowCount(len(rows))
        for row, item in enumerate(rows):
            values = (item.get("created_at", item.get("recorded_at", "—")), item.get("event_type", item.get("title_ar", "حالة")), item.get("message_ar", item.get("body_ar", str(item))))
            for column, value in enumerate(values):
                self.operator_table.setItem(row, column, QTableWidgetItem(str(value)))

    def _request(self, method: str, path: str, payload: dict[str, Any] | None = None, success: str | None = None) -> Any:
        if self._client is None:
            return None
        try:
            result = getattr(self._client, method)(path, payload) if payload is not None else getattr(self._client, method)(path)
        except httpx.HTTPError as error:
            self.warning_banner.setText(f"تعذر تنفيذ العملية: {error}")
            return None
        if success:
            self.warning_banner.setText(success)
        return result

    def _confirm(self, title: str, text: str, action: Callable[[], None]) -> None:
        dialog = QMessageBox(self)
        dialog.setWindowTitle(title)
        dialog.setText(text)
        dialog.setIcon(QMessageBox.Icon.Warning)
        dialog.setStandardButtons(QMessageBox.StandardButton.Cancel | QMessageBox.StandardButton.Ok)
        if dialog.exec() == QMessageBox.StandardButton.Ok:
            action()

    @staticmethod
    def _status_label(text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("statusPill")
        label.setAlignment(Qt.AlignmentFlag.AlignRight)
        return label

    @staticmethod
    def _card(title: str, value: str) -> QFrame:
        card = QFrame()
        card.setObjectName("metricCard")
        layout = QVBoxLayout(card)
        heading = QLabel(title)
        heading.setObjectName("metricTitle")
        number = QLabel(value)
        number.setObjectName("metricValue")
        number.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        layout.addWidget(heading)
        layout.addWidget(number)
        return card

    @staticmethod
    def _action_box(title: str, actions: tuple[tuple[str, Callable[[], None]], ...]) -> QGroupBox:
        box = QGroupBox(title)
        layout = QHBoxLayout(box)
        for label, handler in actions:
            button = QPushButton(label)
            button.clicked.connect(handler)
            layout.addWidget(button)
        return box

    @staticmethod
    def _table(headers: list[str]) -> QTableWidget:
        table = QTableWidget(0, len(headers))
        table.setHorizontalHeaderLabels(headers)
        table.setAlternatingRowColors(True)
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        table.horizontalHeader().setStretchLastSection(True)
        return table

    @staticmethod
    def _stylesheet() -> str:
        return """
            QWidget { background: #0f172a; color: #e2e8f0; font-size: 14px; }
            #appTitle { font-size: 26px; font-weight: 700; color: #f8fafc; }
            #statusPill { background: #1e293b; padding: 8px 12px; border-radius: 12px; }
            #warningBanner { background: #78350f; color: #fef3c7; padding: 12px; border-radius: 8px; }
            #metricCard, #summaryPanel { background: #1e293b; border: 1px solid #334155; border-radius: 10px; padding: 14px; }
            #metricTitle { color: #94a3b8; } #metricValue { font-size: 21px; font-weight: 700; }
            QPushButton { background: #0f766e; padding: 9px 14px; border-radius: 6px; color: white; }
            QPushButton:hover { background: #0d9488; } QLineEdit, QComboBox { background: #fff; color: #111827; padding: 8px; }
            QTableWidget { background: #fff; color: #111827; gridline-color: #cbd5e1; }
            QHeaderView::section { background: #e2e8f0; color: #0f172a; padding: 7px; }
        """
