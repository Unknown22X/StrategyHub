"""Arabic-first native PySide6 control room for RangeBot."""

from collections.abc import Callable
import logging
from pathlib import Path
import sys
from typing import Any

import httpx
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFontDatabase
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from rangebot.domain.runtime import RuntimeState
from rangebot.ui.client import EngineClient

LTR_OPEN = "\u2066"
LTR_CLOSE = "\u2069"
LOGGER = logging.getLogger(__name__)


def _asset_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS")) / "rangebot" / "assets"
    return Path(__file__).resolve().parents[1] / "assets"


def load_arabic_font() -> str:
    """Load bundled Thmanyah Sans and return a safe family fallback."""
    families: list[str] = []
    for path in sorted((_asset_root() / "fonts").glob("ThmanyahSans-*.otf")):
        font_id = QFontDatabase.addApplicationFont(str(path))
        if font_id >= 0:
            families.extend(QFontDatabase.applicationFontFamilies(font_id))
    return families[0] if families else "Segoe UI"


class RangeBotWindow(QWidget):
    """Focused trading workspace; the localhost engine remains authoritative."""

    def __init__(
        self,
        fetch_state: Callable[[], RuntimeState],
        refresh_interval_ms: int = 1_000,
        engine_client: EngineClient | None = None,
    ) -> None:
        super().__init__()
        self._fetch_state = fetch_state
        self._client = engine_client
        self._last_market_guard: dict[str, Any] | None = None
        self._last_paper_preview: dict[str, Any] | None = None
        self._last_paper_preview_request: dict[str, Any] | None = None
        self.is_connected = False
        self.setObjectName("appShell")
        self.setWindowTitle("RangeBot | لوحة التحكم بالتداول")
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self.resize(1440, 900)
        self.setMinimumSize(1100, 720)
        self.set_arabic_font_family(load_arabic_font())
        self.setStyleSheet(self._stylesheet())

        shell = QHBoxLayout(self)
        shell.setContentsMargins(0, 0, 0, 0)
        shell.setSpacing(0)
        shell.addWidget(self._sidebar())

        content = QFrame()
        content.setObjectName("content")
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(28, 24, 28, 24)
        content_layout.setSpacing(14)
        content_layout.addWidget(self._topbar())
        self.warning_banner = QLabel(
            "Live مقفل افتراضياً — يمكنك فتح الصفحة ومراجعتها بأمان."
        )
        self.warning_banner.setObjectName("safetyBanner")
        self.warning_banner.setWordWrap(True)
        content_layout.addWidget(self.warning_banner)

        self.tabs = QTabWidget()
        self.tabs.tabBar().hide()
        self.tabs.setDocumentMode(True)
        self.tabs.addTab(self._dashboard_page(), "الرئيسية")
        self.tabs.addTab(self._watchlist_page(), "المراقبة")
        self.tabs.addTab(self._decision_page(), "تفاصيل القرار")
        self.tabs.addTab(self._entry_page(), "دخول يدوي")
        self.tabs.addTab(self._position_page(), "المركز والحماية")
        self.tabs.addTab(self._risk_page(), "المخاطر والطوارئ")
        self.tabs.addTab(self._operator_page(), "السجل والمساعدة")
        content_layout.addWidget(self.tabs, 1)
        shell.addWidget(content, 1)
        self._mode_changed()

        self._timer = QTimer(self)
        self._timer.setInterval(refresh_interval_ms)
        self._timer.timeout.connect(self.refresh)
        self._timer.start()
        self.refresh()

    def set_arabic_font_family(self, family: str) -> None:
        font = self.font()
        font.setFamily(family)
        font.setPointSize(11)
        self.setFont(font)

    def _sidebar(self) -> QWidget:
        side = QFrame()
        side.setObjectName("sidebar")
        side.setFixedWidth(238)
        layout = QVBoxLayout(side)
        layout.setContentsMargins(16, 24, 16, 20)
        layout.setSpacing(6)
        brand = QLabel(
            "<b>RangeBot</b><br><span style='color:#758b91'>FUTURES CONTROL</span>"
        )
        brand.setObjectName("brand")
        brand.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        layout.addWidget(brand)
        layout.addSpacing(22)
        labels = (
            ("نظرة عامة", 0),
            ("قائمة المراقبة", 1),
            ("تفاصيل القرار", 2),
            ("فتح صفقة", 3),
            ("المركز والحماية", 4),
            ("المخاطر والطوارئ", 5),
            ("السجل والإعدادات", 6),
        )
        self.nav_buttons: list[QPushButton] = []
        for label, index in labels:
            button = QPushButton(label)
            button.setObjectName("navActive" if index == 0 else "navButton")
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.clicked.connect(
                lambda _checked=False, page=index: self._navigate(page)
            )
            layout.addWidget(button)
            self.nav_buttons.append(button)
        layout.addStretch()
        self.sidebar_status = QLabel("● المحرك قيد التحقق")
        self.sidebar_status.setObjectName("engineStatus")
        self.sidebar_status.setWordWrap(True)
        layout.addWidget(self.sidebar_status)
        self.emergency_button = QPushButton("إيقاف طارئ")
        self.emergency_button.setObjectName("emergencyButton")
        self.emergency_button.clicked.connect(self.emergency_stop)
        layout.addWidget(self.emergency_button)
        return side

    def _navigate(self, index: int) -> None:
        self.tabs.setCurrentIndex(index)
        for current, button in enumerate(self.nav_buttons):
            button.setObjectName("navActive" if current == index else "navButton")
            button.style().unpolish(button)
            button.style().polish(button)

    def _topbar(self) -> QWidget:
        bar = QFrame()
        bar.setObjectName("topbar")
        layout = QHBoxLayout(bar)
        title_box = QVBoxLayout()
        title = QLabel("صباح الخير، Jory")
        title.setObjectName("pageTitle")
        subtitle = QLabel("اختر عقداً، اضبط الصفقة، ثم راقب الحماية من مكان واحد.")
        subtitle.setObjectName("muted")
        title_box.addWidget(title)
        title_box.addWidget(subtitle)
        layout.addLayout(title_box)
        layout.addStretch()
        self.connection_label = self._status_label("الاتصال: جارٍ التحقق")
        self.lifecycle_label = self._status_label("المحرك: —")
        self.mode_label = self._status_label("النمط: Paper")
        self.mode_selector = QComboBox()
        self.mode_selector.setObjectName("modeSelector")
        self.mode_selector.addItem("Paper", "paper")
        self.mode_selector.addItem("Gate.io Testnet", "testnet")
        self.mode_selector.addItem("Live — مقفل", "live")
        self.mode_selector.currentIndexChanged.connect(self._mode_changed)
        layout.addWidget(self.connection_label)
        layout.addWidget(self.mode_selector)
        return bar

    def _scroll_page(self, body: QWidget) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidget(body)
        layout.addWidget(scroll)
        return page

    def _dashboard_page(self) -> QWidget:
        body = QWidget()
        layout = QVBoxLayout(body)
        layout.setContentsMargins(0, 0, 0, 8)
        layout.setSpacing(14)

        picker = self._panel("ابدأ باختيار العقد")
        picker_layout = picker.layout()
        pick_row = QHBoxLayout()
        self.contract_input = QLineEdit()
        self.contract_input.setPlaceholderText("ابحث عن عقد مثل BTC_USDT")
        self.contract_input.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        self.contract_input.setClearButtonEnabled(True)
        choose = QPushButton("اختر عملة للبدء")
        choose.setObjectName("primaryButton")
        choose.clicked.connect(self.choose_contract)
        pick_row.addWidget(self.contract_input, 1)
        pick_row.addWidget(choose)
        picker_layout.addLayout(pick_row)
        self.active_contract_label = QLabel("لم يتم اختيار عقد بعد")
        self.active_contract_label.setObjectName("emptyHint")
        picker_layout.addWidget(self.active_contract_label)
        layout.addWidget(picker)

        metrics = QHBoxLayout()
        self.balance_card = self._metric("الرصيد المتاح", "— USDT")
        self.position_card = self._metric("المركز الحالي", "لا يوجد مركز")
        self.protection_card = self._metric("الحماية", "TP / SL —")
        self.risk_card = self._metric("حالة الأمان", "بانتظار المصالحة")
        self.active_card = self._metric("العقد النشط", "—")
        self.cooldown_card = self._metric("المراقبة", "متوقفة")
        for card in (
            self.balance_card,
            self.position_card,
            self.protection_card,
            self.risk_card,
        ):
            metrics.addWidget(card)
        layout.addLayout(metrics)

        main_row = QHBoxLayout()
        main_row.setSpacing(14)
        main_row.addWidget(self._trade_panel(), 5)
        main_row.addWidget(self._watch_panel(), 3)
        layout.addLayout(main_row)

        bottom = QHBoxLayout()
        bottom.addWidget(self._position_panel(), 3)
        bottom.addWidget(self._activity_panel(), 2)
        layout.addLayout(bottom)
        return self._scroll_page(body)

    def _trade_panel(self) -> QWidget:
        panel = self._panel("فتح صفقة يدوية")
        form = QGridLayout()
        self.entry_type = QComboBox()
        self.entry_type.addItems(("Market", "Limit"))
        self.entry_quantity = QLineEdit("0.001")
        self.entry_quantity.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        self.entry_price = QLineEdit()
        self.entry_price.setPlaceholderText("سعر Limit")
        self.entry_price.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        self.entry_allocation = QComboBox()
        self.entry_allocation.addItems(("25%", "50%", "75%", "100%"))
        self.leverage = QComboBox()
        self.leverage.addItems(("1", "5", "10"))
        self.leverage.setCurrentText("5")
        self.take_profit = QLineEdit("10")
        self.stop_loss = QLineEdit("10")
        fields = (
            ("نوع الأمر", self.entry_type),
            ("الكمية (Testnet / Live)", self.entry_quantity),
            ("سعر Limit", self.entry_price),
            ("نسبة الرصيد", self.entry_allocation),
            ("الرافعة", self.leverage),
            ("TP %", self.take_profit),
            ("SL %", self.stop_loss),
        )
        for index, (label, widget) in enumerate(fields):
            form.addWidget(QLabel(label), index // 2, (index % 2) * 2)
            form.addWidget(widget, index // 2, (index % 2) * 2 + 1)
        panel.layout().addLayout(form)
        self.preview_summary = QLabel(
            "اختر عقداً أولاً. ستظهر هنا معاينة الرسوم والمخاطر قبل التأكيد."
        )
        self.preview_summary.setObjectName("previewBox")
        self.preview_summary.setWordWrap(True)
        panel.layout().addWidget(self.preview_summary)
        buttons = QHBoxLayout()
        monitor = QPushButton("بدء المراقبة")
        monitor.setObjectName("monitorButton")
        monitor.clicked.connect(self.start_monitoring)
        long_button = QPushButton("شراء / Long")
        long_button.setObjectName("longButton")
        long_button.clicked.connect(lambda: self.submit_direction("long"))
        short_button = QPushButton("بيع / Short")
        short_button.setObjectName("shortButton")
        short_button.clicked.connect(lambda: self.submit_direction("short"))
        buttons.addWidget(monitor)
        buttons.addWidget(long_button)
        buttons.addWidget(short_button)
        panel.layout().addLayout(buttons)
        auto = QCheckBox("تداول تلقائي لهذا العقد — يتطلب تأكيداً منفصلاً")
        auto.setObjectName("autoToggle")
        panel.layout().addWidget(auto)
        self.auto_toggle = auto
        self.auto_toggle.stateChanged.connect(self._automatic_toggled)
        self.entry_direction = QComboBox()
        self.entry_direction.addItem("شراء / Long", "long")
        self.entry_direction.addItem("بيع / Short", "short")
        return panel

    def _watch_panel(self) -> QWidget:
        panel = self._panel("قائمة المراقبة")
        self.watchlist_table = self._table(["العقد", "السعر", "الحالة"])
        self.watchlist_table.setMaximumHeight(250)
        self.watchlist_table.cellClicked.connect(self._watchlist_clicked)
        panel.layout().addWidget(self.watchlist_table)
        self.watchlist_message = QLabel("أضف عقداً أو اختره من القائمة للبدء.")
        self.watchlist_message.setObjectName("muted")
        panel.layout().addWidget(self.watchlist_message)
        return panel

    def _position_panel(self) -> QWidget:
        panel = self._panel("المركز والحماية")
        self.position_summary = QLabel(
            "لا يوجد مركز مفتوح. ستظهر الكمية وTP وSL هنا بعد التنفيذ."
        )
        self.position_summary.setWordWrap(True)
        self.position_summary.setObjectName("positionSummary")
        panel.layout().addWidget(self.position_summary)
        row = QHBoxLayout()
        refresh = QPushButton("تحديث المركز")
        refresh.clicked.connect(self.load_position)
        protect = QPushButton("فحص الحماية")
        protect.clicked.connect(self.check_protection)
        close = QPushButton("إغلاق المركز")
        close.setObjectName("dangerButton")
        close.clicked.connect(self.close_position)
        for button in (refresh, protect, close):
            row.addWidget(button)
        panel.layout().addLayout(row)
        return panel

    def _activity_panel(self) -> QWidget:
        panel = self._panel("آخر النشاط")
        self.activity_label = QLabel(
            "● الواجهة جاهزة\n\n● لم يتم إرسال أي أمر\n\n● Live مقفل"
        )
        self.activity_label.setWordWrap(True)
        self.activity_label.setObjectName("activityFeed")
        panel.layout().addWidget(self.activity_label)
        return panel

    def _watchlist_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        controls = QHBoxLayout()
        self.symbol_input = QLineEdit()
        self.symbol_input.setPlaceholderText("BTC_USDT")
        self.symbol_input.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        add = QPushButton("إضافة للمراقبة")
        add.clicked.connect(self.add_watchlist)
        active = QPushButton("تعيين كنشط")
        active.clicked.connect(self.activate_watchlist)
        controls.addWidget(self.symbol_input, 1)
        controls.addWidget(add)
        controls.addWidget(active)
        layout.addLayout(controls)
        self.watchlist_full_table = self._table(
            ["العقد", "آخر سعر", "الاتجاه", "الحداثة"]
        )
        layout.addWidget(self.watchlist_full_table)
        return page

    def _decision_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.addWidget(
            QLabel("شروط القرار تُعرض بالعربية ولا يمكن للواجهة تجاوز أي شرط أمان.")
        )
        self.decision_table = self._table(["الشرط", "الحالة", "التفسير"])
        layout.addWidget(self.decision_table)
        return page

    def _entry_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.addWidget(
            QLabel(
                "تم نقل مسار الدخول إلى اللوحة الرئيسية ليبقى الإجراء الأساسي واضحاً."
            )
        )
        go = QPushButton("العودة إلى لوحة التداول")
        go.setObjectName("primaryButton")
        go.clicked.connect(lambda: self._navigate(0))
        layout.addWidget(go)
        layout.addStretch()
        return page

    def _position_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.addWidget(self._position_panel())
        form = QFormLayout()
        self.protection_confirmation = QLineEdit()
        self.protection_confirmation.setPlaceholderText("DISABLE TP أو DISABLE SL")
        form.addRow("تأكيد مكتوب", self.protection_confirmation)
        buttons = QHBoxLayout()
        tp = QPushButton("تعطيل TP")
        tp.clicked.connect(self.disable_live_tp)
        sl = QPushButton("تعطيل SL")
        sl.clicked.connect(self.disable_live_sl)
        buttons.addWidget(tp)
        buttons.addWidget(sl)
        form.addRow(buttons)
        layout.addLayout(form)
        layout.addStretch()
        return page

    def _risk_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        self.risk_summary = QLabel("حالة المخاطر ستظهر بعد تحديث الحساب.")
        self.risk_summary.setObjectName("previewBox")
        layout.addWidget(self.risk_summary)
        row = QHBoxLayout()
        for label, handler in (
            ("تحديث المخاطر", self.load_risk),
            ("استئناف آمن", self.resume_emergency),
            ("إغلاق طارئ", self.emergency_close),
        ):
            button = QPushButton(label)
            button.clicked.connect(handler)
            row.addWidget(button)
        layout.addLayout(row)
        layout.addStretch()
        return page

    def _operator_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        api_panel = self._panel("اتصال Gate.io الآمن")
        api_note = QLabel(
            "تُحفظ المفاتيح في ملف .env محلي بصلاحيات Windows مقيدة. لا تُعرض بعد الحفظ ولا تستخدمها الواجهة مباشرة."
        )
        api_note.setWordWrap(True)
        api_note.setObjectName("muted")
        api_panel.layout().addWidget(api_note)
        api_form = QFormLayout()
        self.api_mode = QComboBox()
        self.api_mode.addItem("Gate.io Testnet", "testnet")
        self.api_mode.addItem("Live", "live")
        self.api_key = QLineEdit()
        self.api_key.setEchoMode(QLineEdit.EchoMode.Password)
        self.api_secret = QLineEdit()
        self.api_secret.setEchoMode(QLineEdit.EchoMode.Password)
        api_form.addRow("الحساب", self.api_mode)
        api_form.addRow("API Key", self.api_key)
        api_form.addRow("API Secret", self.api_secret)
        save = QPushButton("حفظ المفاتيح بأمان")
        save.clicked.connect(self.save_api_credentials)
        api_form.addRow(save)
        api_panel.layout().addLayout(api_form)
        layout.addWidget(api_panel)
        live_panel = self._panel("فتح وضع Live")
        self.live_confirmation = QLineEdit()
        self.live_confirmation.setPlaceholderText("اكتب LIVE")
        unlock = QPushButton("فتح Live")
        unlock.setObjectName("dangerButton")
        unlock.clicked.connect(self.activate_live)
        live_panel.layout().addWidget(
            QLabel("التحقق من Paper وTestnet استشاري فقط ولا يمنع فتح Live.")
        )
        live_panel.layout().addWidget(self.live_confirmation)
        live_panel.layout().addWidget(unlock)
        layout.addWidget(live_panel)
        self.operator_table = self._table(["الوقت", "الحدث", "الشرح"])
        layout.addWidget(self.operator_table)
        actions = QHBoxLayout()
        for label, handler in (
            ("تحميل السجل", self.load_audit),
            ("مصالحة الحساب", self.reconcile_selected_exchange),
        ):
            button = QPushButton(label)
            button.clicked.connect(handler)
            actions.addWidget(button)
        layout.addLayout(actions)
        return page

    def choose_contract(self) -> None:
        symbol = self.contract_input.text().strip().upper()
        if not symbol:
            self._show_message("اختر عقداً", "اكتب رمز العقد أولاً، مثل BTC_USDT.")
            return
        self.symbol_input.setText(symbol)
        self._last_paper_preview = None
        self._last_paper_preview_request = None
        self.active_contract_label.setText(f"العقد النشط: {self._ltr(symbol)}")
        self._metric_value(self.active_card, symbol)
        self.preview_summary.setText(
            "العقد جاهز. اضبط الكمية والحماية ثم اختر شراء أو بيع."
        )

    def _watchlist_clicked(self, row: int, _column: int) -> None:
        item = self.watchlist_table.item(row, 0)
        if item:
            self.contract_input.setText(item.text())
            self.choose_contract()

    def submit_direction(self, direction: str) -> None:
        self.entry_direction.setCurrentIndex(0 if direction == "long" else 1)
        if not self.contract_input.text().strip():
            self._show_message("لم يتم اختيار عقد", "اختر عملة للبدء قبل فتح الصفقة.")
            return
        self.create_preview()
        self.submit_market_entry()

    def refresh(self) -> None:
        try:
            state = self._fetch_state()
        except Exception:
            self.is_connected = False
            self.connection_label.setText("الاتصال: غير متاح")
            self.sidebar_status.setText("● المحرك غير متصل")
            return
        self.is_connected = True
        self.connection_label.setText("الاتصال: متصل")
        self.sidebar_status.setText("● المحرك متصل ويستقبل البيانات")
        self.lifecycle_label.setText(f"المحرك: {self._ltr(state.lifecycle)}")

    def refresh_all(self) -> None:
        self.refresh()
        self.load_watchlist()
        self.load_position()

    def _mode_changed(self) -> None:
        mode = str(self.mode_selector.currentData())
        self._last_paper_preview = None
        self._last_paper_preview_request = None
        self.entry_quantity.setEnabled(mode != "paper")
        self.entry_quantity.setToolTip(
            "تُحسب كمية Paper من نسبة الرصيد" if mode == "paper" else "كمية العقد"
        )
        names = {"paper": "Paper", "testnet": "Testnet", "live": "Live"}
        self.mode_label.setText(f"النمط: {names[mode]}")
        if mode == "live":
            self.warning_banner.setText(
                "Live مقفل حتى تكتب LIVE. فتح الصفحة لا يرسل أي أمر."
            )
        else:
            self.warning_banner.setText(
                f"أنت الآن في {names[mode]}. الحالات بين الحسابات منفصلة."
            )

    def create_preview(self) -> None:
        mode = str(self.mode_selector.currentData())
        if mode == "paper":
            self._last_paper_preview = None
            self._last_paper_preview_request = None
            symbol = self.contract_input.text().strip().upper()
            account = self._request("get", "/v1/paper-account")
            watchlist = self._request("get", "/v1/paper/watchlist")
            contracts = self._request("get", f"/v1/paper/contracts?query={symbol}")
            items = watchlist.get("items", []) if isinstance(watchlist, dict) else []
            selected = next(
                (item for item in items if item.get("symbol") == symbol), None
            )
            contract = (
                contracts[0] if isinstance(contracts, list) and contracts else None
            )
            if (
                not isinstance(account, dict)
                or selected is None
                or selected.get("last_price") is None
                or contract is None
            ):
                self.warning_banner.setText(
                    "حدّث حساب Paper وبيانات العقد قبل إنشاء المعاينة."
                )
                return
            request = {
                "available_futures_balance": account["available_futures_balance"],
                "allocation_percentage": self.entry_allocation.currentText().rstrip(
                    "%"
                ),
                "safety_reserve_percentage": "10",
                "leverage": int(self.leverage.currentText()),
                "expected_entry_price": selected["last_price"],
                "quantity_step": contract["quantity_step"],
                "minimum_quantity": contract["minimum_quantity"],
                "direction": self.entry_direction.currentData(),
                "quote_revision": f"ui-{self.contract_input.text().strip().upper()}",
                "take_profit_percentage": self.take_profit.text(),
                "stop_loss_percentage": self.stop_loss.text(),
            }
            result = self._request("post", "/v1/paper/entry-preview", request)
            if isinstance(result, dict):
                self._last_paper_preview_request = request
                self._last_paper_preview = result
                self.preview_summary.setText(
                    f"الكمية المحسوبة: {self._ltr(str(result.get('quantity', '—')))} • "
                    f"TP: {self._ltr(str(result.get('take_profit_price', '—')))} • "
                    f"SL: {self._ltr(str(result.get('stop_loss_price', '—')))}"
                )
            return
        payload = {
            "symbol": self.contract_input.text().strip().upper() or "BTC_USDT",
            "direction": self.entry_direction.currentData(),
            "quantity": self.entry_quantity.text(),
        }
        result = self._request(
            "post", f"/v1/exchange/{mode}/market-guard-quote", payload
        )
        if isinstance(result, dict):
            self._last_market_guard = result
            self.preview_summary.setText(
                "بيانات السوق حديثة والسيولة قيد الفحص النهائي عند الإرسال."
            )

    def submit_market_entry(self) -> None:
        mode = str(self.mode_selector.currentData())
        symbol = self.contract_input.text().strip().upper()
        if not symbol:
            return
        if mode == "paper":
            if self._last_paper_preview is None:
                self.create_preview()
            if (
                self._last_paper_preview is None
                or self._last_paper_preview_request is None
            ):
                return
            payload = {
                "preview": self._last_paper_preview,
                "current_request": self._last_paper_preview_request,
                "confirmation": "CONFIRM PAPER MARKET ENTRY",
            }
            self._confirm(
                "تأكيد صفقة Paper",
                "سيتم فتح مركز محاكاة فقط وتطبيق TP وSL المعروضين.",
                lambda: self._request(
                    "post",
                    "/v1/paper/market-entry",
                    payload,
                    "تم فتح مركز Paper المحاكى.",
                ),
            )
            return
        payload: dict[str, Any] = {
            "symbol": symbol,
            "direction": self.entry_direction.currentData(),
            "order_type": self.entry_type.currentText().lower(),
            "quantity": self.entry_quantity.text(),
            "protections_enabled": True,
            "take_profit_percentage": self.take_profit.text(),
            "stop_loss_percentage": self.stop_loss.text(),
            "leverage": int(self.leverage.currentText()),
        }
        if payload["order_type"] == "limit":
            payload["limit_price"] = self.entry_price.text()
        self._confirm(
            "تأكيد أمر التداول",
            f"راجع العقد {symbol} والكمية والاتجاه. سيعيد المحرك فحص السوق والأمان فوراً.",
            lambda: self._request(
                "post",
                f"/v1/exchange/{mode}/entries",
                payload,
                "تم قبول الطلب من المحرك.",
            ),
        )

    def add_watchlist(self) -> None:
        symbol = self.symbol_input.text().strip().upper()
        if symbol:
            self._request("post", "/v1/paper/watchlist", {"symbol": symbol})
            self.load_watchlist()

    def activate_watchlist(self) -> None:
        symbol = self.symbol_input.text().strip().upper()
        if symbol:
            self.contract_input.setText(symbol)
            self.choose_contract()

    def start_automation(self) -> None:
        symbol = self.contract_input.text().strip().upper()
        if not symbol:
            self._show_message("لم يتم اختيار عقد", "اختر عقداً قبل بدء المراقبة.")
            return
        mode = str(self.mode_selector.currentData())
        if mode == "paper":
            path, payload = "/v1/paper/automatic-trading/start", None
        else:
            path, payload = (
                f"/v1/exchange/{mode}/automatic/start",
                {"active_contract": symbol},
            )
        result = self._confirm(
            "تأكيد التداول التلقائي",
            f"سيُفعّل التداول التلقائي للعقد {symbol} في نمط {mode}. راجع المخاطر والحماية أولاً.",
            lambda: self._request("post", path, payload, "بدأت المراقبة."),
        )
        self.auto_toggle.blockSignals(True)
        self.auto_toggle.setChecked(isinstance(result, dict))
        self.auto_toggle.setEnabled(not isinstance(result, dict))
        if isinstance(result, dict):
            self.auto_toggle.setText(
                "التداول التلقائي مفعّل — أوقفه من صفحة المخاطر بعد المصالحة"
            )
        self.auto_toggle.blockSignals(False)

    def start_monitoring(self) -> None:
        symbol = self.contract_input.text().strip().upper()
        if not symbol:
            self._show_message("لم يتم اختيار عقد", "اختر عقداً قبل بدء المراقبة.")
            return
        self.symbol_input.setText(symbol)
        self._metric_value(self.cooldown_card, "نشطة")
        self.activity_label.setText(
            f"● بدأت مراقبة {self._ltr(symbol)}\n\n● التداول التلقائي غير مفعّل\n\n● لم يتم إرسال أي أمر"
        )

    def _automatic_toggled(self, state: int) -> None:
        if state == Qt.CheckState.Checked.value:
            self.auto_toggle.blockSignals(True)
            self.auto_toggle.setChecked(False)
            self.auto_toggle.blockSignals(False)
            self.start_automation()

    def load_watchlist(self) -> None:
        result = self._request("get", "/v1/paper/watchlist")
        if not isinstance(result, dict):
            return
        items = result.get("items", [])
        for table in (self.watchlist_table, self.watchlist_full_table):
            table.setRowCount(len(items))
        for row, item in enumerate(items):
            symbol = str(item.get("symbol", ""))
            values = (
                symbol,
                str(item.get("last_price", "—")),
                "نشط" if item.get("is_active") else "مراقبة",
            )
            for column, value in enumerate(values):
                self.watchlist_table.setItem(row, column, QTableWidgetItem(value))
            full = (
                symbol,
                str(item.get("last_price", "—")),
                str(item.get("direction", "both")),
                str(item.get("freshness", "—")),
            )
            for column, value in enumerate(full):
                self.watchlist_full_table.setItem(row, column, QTableWidgetItem(value))

    def load_position(self) -> None:
        mode = str(self.mode_selector.currentData())
        result = self._request(
            "get",
            "/v1/paper/position" if mode == "paper" else f"/v1/exchange/{mode}/state",
        )
        if isinstance(result, dict):
            snapshot = result.get("snapshot", result) or {}
            quantity = snapshot.get("quantity", snapshot.get("position_quantity", "0"))
            self.position_summary.setText(
                f"الكمية: {self._ltr(str(quantity))}  •  الحماية: {self._ltr('TP / SL')}"
            )

    def check_protection(self) -> None:
        mode = str(self.mode_selector.currentData())
        if mode != "paper":
            self._request(
                "post",
                f"/v1/exchange/{mode}/protection/check",
                success="تم فحص الحماية.",
            )

    def disable_live_tp(self) -> None:
        self._change_live_protection("tp", "DISABLE TP")

    def disable_live_sl(self) -> None:
        self._change_live_protection("sl", "DISABLE SL")

    def _change_live_protection(self, protection: str, expected: str) -> None:
        self._request(
            "post",
            "/v1/live/protection",
            {
                "protection": protection,
                "enabled": False,
                "confirmation": self.protection_confirmation.text() or expected,
            },
        )

    def close_position(self) -> None:
        mode = str(self.mode_selector.currentData())
        if mode != "paper":
            self._confirm(
                "إغلاق المركز",
                "سيغلق المحرك الكمية المُدارة فقط.",
                lambda: self._request(
                    "post",
                    f"/v1/exchange/{mode}/close",
                    {"confirmation": "CLOSE POSITION"},
                ),
            )

    def cancel_pending(self) -> None:
        mode = str(self.mode_selector.currentData())
        if mode != "paper":
            self._request("post", f"/v1/exchange/{mode}/cancel-entry")

    def load_risk(self) -> None:
        result = self._request("get", "/v1/paper/risk")
        if isinstance(result, dict):
            self.risk_summary.setText("حدود المخاطر محدثة. راجع السجل لأي سبب منع.")

    def emergency_stop(self) -> None:
        mode = str(self.mode_selector.currentData())
        path = (
            "/v1/paper/emergency-stop"
            if mode == "paper"
            else f"/v1/exchange/{mode}/emergency-stop"
        )
        payload = (
            {"confirmation": "EMERGENCY STOP", "reason": "طلب من واجهة التحكم"}
            if mode == "paper"
            else None
        )
        self._confirm(
            "إيقاف طارئ",
            "سيُمنع أي دخول جديد وتُلغى الأوامر المُدارة فقط.",
            lambda: self._request("post", path, payload, "تم تفعيل الإيقاف الطارئ."),
        )

    def emergency_close(self) -> None:
        mode = str(self.mode_selector.currentData())
        if mode != "paper":
            self._confirm(
                "إغلاق طارئ",
                "سيُفعّل الإيقاف أولاً ثم يُغلق المركز المُدار.",
                lambda: self._request("post", f"/v1/exchange/{mode}/emergency-close"),
            )

    def resume_emergency(self) -> None:
        mode = str(self.mode_selector.currentData())
        if mode != "paper":
            self._request("post", f"/v1/exchange/{mode}/resume?confirmation=RESUME")

    def reconcile_selected_exchange(self) -> None:
        mode = str(self.mode_selector.currentData())
        if mode != "paper":
            self._request(
                "post",
                f"/v1/exchange/{mode}/reconcile",
                success="اكتملت المصالحة الآمنة.",
            )

    def activate_live(self) -> None:
        self._request(
            "post",
            "/v1/live/activate",
            {"confirmation": self.live_confirmation.text()},
            "تم فتح Live. ستظل أوامر التداول خاضعة لفحوص الأمان الفورية.",
        )

    def save_api_credentials(self) -> None:
        payload = {
            "mode": self.api_mode.currentData(),
            "api_key": self.api_key.text(),
            "api_secret": self.api_secret.text(),
        }
        result = self._request("post", "/v1/exchange/credentials", payload)
        if isinstance(result, dict):
            self.api_key.clear()
            self.api_secret.clear()
            self.warning_banner.setText(
                "تم حفظ مفاتيح API محلياً بصلاحيات مقيدة. أعد تشغيل خدمة المحرك لتطبيقها."
            )

    def load_audit(self) -> None:
        mode = str(self.mode_selector.currentData())
        path = (
            "/v1/paper-account/audit"
            if mode == "paper"
            else f"/v1/exchange/{mode}/operations"
        )
        result = self._request("get", path)
        rows = result if isinstance(result, list) else []
        self.operator_table.setRowCount(len(rows))
        for row, item in enumerate(rows):
            values = (
                str(item.get("created_at", "—")),
                str(item.get("kind", item.get("event_type", "حالة"))),
                str(item.get("message_ar", "تم تسجيل الحدث.")),
            )
            for column, value in enumerate(values):
                self.operator_table.setItem(row, column, QTableWidgetItem(value))

    def _request(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
        success: str | None = None,
    ) -> Any:
        if self._client is None:
            return None
        try:
            function = getattr(self._client, method)
            result = function(path, payload) if payload is not None else function(path)
        except Exception as error:
            status = (
                error.response.status_code
                if isinstance(error, httpx.HTTPStatusError)
                else None
            )
            LOGGER.warning(
                "UI engine request failed (type=%s, status=%s)",
                type(error).__name__,
                status,
            )
            self.warning_banner.setText(self._friendly_error(error))
            return None
        if success:
            self.warning_banner.setText(success)
        return result

    @staticmethod
    def _friendly_error(error: Exception) -> str:
        if isinstance(error, httpx.TimeoutException):
            return "تعذر الوصول إلى المحرك في الوقت المحدد. حاول مرة أخرى."
        if isinstance(error, httpx.ConnectError):
            return "المحرك غير متصل حالياً. شغّل الخدمة ثم أعد المحاولة."
        if isinstance(error, httpx.HTTPStatusError):
            status = error.response.status_code
            messages = {
                401: "بيانات الحساب غير صالحة.",
                409: "الإجراء ممنوع حالياً بسبب حالة الأمان.",
                422: "راجع القيم أو نص التأكيد المطلوب.",
                503: "الخدمة أو بيانات السوق غير جاهزة حالياً.",
            }
            return messages.get(status, "تعذر تنفيذ الإجراء بأمان.")
        return "حدث خطأ غير متوقع. تم تسجيل التفاصيل داخلياً."

    def _confirm(self, title: str, text: str, action: Callable[[], Any]) -> Any:
        dialog = QMessageBox(self)
        dialog.setWindowTitle(title)
        dialog.setText(text)
        dialog.setIcon(QMessageBox.Icon.Warning)
        dialog.setStandardButtons(
            QMessageBox.StandardButton.Cancel | QMessageBox.StandardButton.Ok
        )
        if dialog.exec() == QMessageBox.StandardButton.Ok:
            return action()
        return None

    def _show_message(self, title: str, text: str) -> None:
        QMessageBox.information(self, title, text)

    @staticmethod
    def _status_label(text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("statusPill")
        label.setAlignment(Qt.AlignmentFlag.AlignRight)
        return label

    @staticmethod
    def _panel(title: str) -> QFrame:
        frame = QFrame()
        frame.setObjectName("panel")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(12)
        heading = QLabel(title)
        heading.setObjectName("panelTitle")
        layout.addWidget(heading)
        return frame

    @staticmethod
    def _metric(title: str, value: str) -> QFrame:
        frame = QFrame()
        frame.setObjectName("metricCard")
        layout = QVBoxLayout(frame)
        label = QLabel(title)
        label.setObjectName("metricTitle")
        number = QLabel(value)
        number.setObjectName("metricValue")
        number.setProperty("metricValue", True)
        layout.addWidget(label)
        layout.addWidget(number)
        return frame

    @staticmethod
    def _metric_value(card: QFrame, value: str) -> None:
        labels = card.findChildren(QLabel)
        if len(labels) > 1:
            labels[1].setText(value)

    @staticmethod
    def _table(headers: list[str]) -> QTableWidget:
        table = QTableWidget(0, len(headers))
        table.setHorizontalHeaderLabels(headers)
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        table.horizontalHeader().setStretchLastSection(True)
        table.verticalHeader().hide()
        return table

    @staticmethod
    def _ltr(value: str) -> str:
        return f"{LTR_OPEN}{value}{LTR_CLOSE}"

    @staticmethod
    def _stylesheet() -> str:
        return """
        QWidget { color:#edf4f2; font-size:14px; }
        #appShell, #content, QScrollArea, QScrollArea > QWidget > QWidget { background:#0a1015; }
        #sidebar { background:#0c1419; border-left:1px solid #263842; }
        #brand { font-size:20px; padding:4px 8px; }
        #navButton, #navActive { text-align:right; border:0; border-radius:9px; padding:11px 13px; color:#9eb1b5; background:transparent; }
        #navButton:hover { background:#111e25; color:#edf4f2; }
        #navActive { background:#17252e; color:#ffffff; border-right:3px solid #45d7b1; }
        #engineStatus { background:#101a21; border:1px solid #263842; border-radius:11px; padding:12px; color:#9ee9d6; }
        #topbar { background:transparent; }
        #pageTitle { font-size:25px; font-weight:700; }
        #muted, #emptyHint { color:#8fa4a9; }
        #statusPill, #modeSelector { background:#101a21; border:1px solid #263842; border-radius:16px; padding:8px 12px; }
        #safetyBanner { background:#171b19; border:1px solid #5f5037; color:#f4d392; border-radius:11px; padding:11px 15px; }
        #panel, #metricCard { background:#111c23; border:1px solid #263842; border-radius:14px; }
        #panelTitle { font-size:16px; font-weight:700; }
        #metricCard { min-height:82px; padding:12px; }
        #metricTitle { color:#8fa4a9; font-size:12px; }
        #metricValue { font-size:17px; font-weight:700; }
        #previewBox, #positionSummary, #activityFeed { background:#0d171d; border:1px solid #20323b; border-radius:9px; padding:12px; color:#b9cbcd; }
        QLineEdit, QComboBox, QSpinBox { background:#0d171d; border:1px solid #2a3d46; border-radius:8px; padding:9px 10px; color:#edf4f2; selection-background-color:#286b5d; }
        QLineEdit:focus, QComboBox:focus, QSpinBox:focus { border-color:#45d7b1; }
        QPushButton { background:#1a2a34; border:1px solid #304650; border-radius:8px; padding:9px 13px; color:#dce8e7; font-weight:600; }
        QPushButton:hover { background:#223640; border-color:#47707a; }
        #primaryButton, #monitorButton { background:#176e5d; border-color:#2e9c83; color:white; }
        #longButton { background:#1d806b; border-color:#38a98c; color:white; font-size:15px; }
        #shortButton { background:#a84d4d; border-color:#cf6862; color:white; font-size:15px; }
        #dangerButton, #emergencyButton { background:#3b2225; border-color:#7b454a; color:#ffb8b2; }
        #autoToggle { background:#0d171d; border-radius:8px; padding:10px; color:#f2c776; }
        QTableWidget { background:#0d171d; alternate-background-color:#101d24; border:1px solid #263842; border-radius:8px; gridline-color:#263842; selection-background-color:#1b4d45; }
        QHeaderView::section { background:#18262e; color:#9fb2b6; border:0; border-bottom:1px solid #30434b; padding:9px; font-weight:600; }
        QScrollBar:vertical { background:#0d151a; width:10px; }
        QScrollBar::handle:vertical { background:#2a4048; border-radius:5px; min-height:30px; }
        """
