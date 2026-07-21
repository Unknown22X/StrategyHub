from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
FRONTEND = ROOT / "frontend" / "src"


def test_frontend_operations_use_backend_endpoints_and_no_live_lock_contract() -> None:
    types = (FRONTEND / "types.ts").read_text(encoding="utf-8")
    api = (FRONTEND / "api.ts").read_text(encoding="utf-8")
    app = (FRONTEND / "App.tsx").read_text(encoding="utf-8")
    drawer = (FRONTEND / "components" / "OperationsDrawer.tsx").read_text(
        encoding="utf-8"
    )
    connection = (FRONTEND / "components" / "GateConnectionDrawer.tsx").read_text(
        encoding="utf-8"
    )
    detail = (FRONTEND / "components" / "StrategyDetailPage.tsx").read_text(
        encoding="utf-8"
    )
    customize = (FRONTEND / "components" / "DashboardCustomizeDrawer.tsx").read_text(
        encoding="utf-8"
    )
    layout = (FRONTEND / "dashboardLayout.ts").read_text(encoding="utf-8")
    filters = (FRONTEND / "dashboardFilters.ts").read_text(encoding="utf-8")
    filter_bar = (FRONTEND / "components" / "DashboardFilterBar.tsx").read_text(
        encoding="utf-8"
    )
    chart = (FRONTEND / "components" / "StrategyChart.tsx").read_text(encoding="utf-8")
    trade_history = (FRONTEND / "components" / "TradeHistoryPage.tsx").read_text(
        encoding="utf-8"
    )
    risk_management = (FRONTEND / "components" / "RiskManagementDrawer.tsx").read_text(
        encoding="utf-8"
    )
    manual_trade = (FRONTEND / "components" / "ManualTradeDrawer.tsx").read_text(
        encoding="utf-8"
    )
    environment_selector = (
        FRONTEND / "components" / "EnvironmentSelector.tsx"
    ).read_text(encoding="utf-8")
    dashboard_hook = (FRONTEND / "hooks" / "useDashboard.ts").read_text(
        encoding="utf-8"
    )

    assert "live_locked" not in types + app
    assert '"/v1/backups"' in api
    assert "/v1/logs/export" in api
    assert "OperationsDrawer" in app
    assert "النسخ الاحتياطية والسجلات" in app
    assert "RESTORE RANGEBOT" in drawer
    assert "window.confirm" in drawer
    assert "onRestored" in drawer
    assert "/v1/exchange/credentials" in api
    assert "/credentials/test" in api
    assert "removeCredentials" in connection
    assert 'autoComplete="new-password"' in connection
    assert "Credential Profile" in connection
    assert "localStorage" not in connection
    assert "/v1/runtime/environment/switch" in api
    assert "switchRuntimeEnvironment" in api + app
    assert "active_engine_environment" in types + app + environment_selector
    assert "public_rest_environment" in types
    assert "exchange_adapter_environment" in types + manual_trade
    assert "LIVE — REAL FUNDS" in environment_selector + manual_trade
    assert "environmentReady" in manual_trade
    assert "Minimum Quantity" in manual_trade
    assert "Approx. Minimum Margin" in manual_trade
    assert "/duplicate" in api
    assert "StrategyConfigurationFields" in detail
    assert "loadStrategyRuns" in detail
    assert "loadStrategyConfigurationVersions" in detail
    assert "window.confirm" in detail
    assert "DashboardCustomizeDrawer" in app
    assert "serializeDashboardLayout" in app
    assert "saveApplicationSettings" in app
    assert "إعادة التخطيط الافتراضي" in customize
    assert "dashboardWidgetLabels" in customize
    assert "hidden" in layout
    assert "density" in layout
    assert "/v1/paper/pending-entry-state" in api
    assert "cancelPaperPendingEntry" in api + app
    assert "paperPendingEntry" in types + app
    assert "strategy_name" in types + app
    assert "orderOwnerLabel" in app
    assert "المالك / المصدر" in app
    assert "الحالة" in app
    assert "DashboardFilterBar" in app
    assert "serializeDashboardFilters" in app
    assert "dashboard_filters" in app
    assert "strategy_id" in filters
    assert "event_type" in filters
    assert "بيئة العرض" in filter_bar
    assert "تطبيق وحفظ" in filter_bar
    assert "/v1/market-data/" in api
    assert "loadMarketCandles" in api + chart
    assert "loadMarketSnapshot" in api + chart
    assert "candlestick-chart" in chart
    assert "supported_timeframes" in types + chart
    assert "chart_overlays" in types + chart
    assert "TradingView" not in chart
    assert "StrategyChart" in app + detail
    assert "supported_timeframes" in types
    assert "required_market_data_feeds" in types
    assert "implementation_status" in types
    assert "/v1/activity?limit=200" in api
    assert "ActivityEvent" in types + app
    assert "سجل موحد ومنقح من المحرك" in app
    assert "الطلبات والتنفيذ" in filter_bar
    assert "الفحص والاختبارات التاريخية" in filter_bar
    assert "/v1/performance/account/" in api
    assert "/v1/performance/account/paper?period=all&maximum_points=2" in api
    assert "paperPerformance" in api + types + app
    assert 'mode: "paper" | "testnet" | "live"' in types
    assert "AccountPerformanceSeries" in types + app
    assert "AccountEquityChart" in app
    assert "أقصى تراجع" in app
    assert "السجل التاريخي لـ Paper غير متاح" not in app
    assert "دفتر Paper المحلي" in app
    assert "requested_margin" in types + detail
    assert "requested_leverage" in types + detail
    assert "الهامش لكل دخول تلقائي" in detail
    assert "الرافعة المطلوبة" in detail
    assert "requested_margin" in (
        FRONTEND / "components" / "StrategyCreateDrawer.tsx"
    ).read_text(encoding="utf-8")
    assert "/v1/strategies/overview" in api
    assert "StrategyOverviewItem" in types + app
    assert "today_realized_pnl" in types + app
    assert "total_realized_pnl" in types + app
    assert "win_rate_percentage" in types + app
    assert "last_trade_at" in types + app
    assert "warning_codes" in types + app
    assert "أداء وتشغيل من المحرك" in app
    assert "نسبة الفوز" in app
    assert "/v1/account-risk/live" in api
    assert "/v1/account-risk/testnet" in api
    assert "AccountRiskStatus" in types + app
    assert "remaining_loss_allowance" in types + app
    assert "خسارة حقوق الملكية اليومية" in app
    assert "الصفقات التلقائية" in app
    assert "RiskManagementDrawer" in app
    assert "loadAccountRiskPolicy" in api + risk_management
    assert "saveAccountRiskPolicy" in api + risk_management
    assert "حفظ حدود المخاطر" in risk_management
    assert "لن يظهر نجاح الحفظ" in risk_management
    assert "localStorage" not in risk_management
    assert "/v1/trades?" in api
    assert "/v1/trades/summary?" in api
    assert "TradeHistoryPage" in app
    assert "سجل التنفيذات" in app
    assert "بيانات تنفيذ غير قابلة لإعادة الكتابة" in trade_history
    assert "Gate.io REST" in trade_history
    assert "Paper Engine" in trade_history
    assert "loadTradeHistorySummary" in detail
    assert "win_rate_percentage" in types + detail
    assert "profit_factor" in types + detail
    assert "أداء التنفيذ المنسوب" in detail
    assert "localStorage" not in trade_history
    assert "gate.com" not in trade_history.lower()
    assert "new WebSocket" in dashboard_hook
    assert "/v1/events" in dashboard_hook
    assert "Math.min(1000 * 2 ** retryCount, 15_000)" in dashboard_hook
    assert "Math.max(refreshIntervalMs, 30_000)" in dashboard_hook
    assert "void refresh()" in dashboard_hook
    assert "readonly code" in api
    assert "readonly context" in api


def test_frontend_does_not_persist_critical_state_in_browser_storage() -> None:
    source = "\n".join(
        path.read_text(encoding="utf-8")
        for path in FRONTEND.rglob("*")
        if path.is_file() and path.suffix in {".ts", ".tsx"}
    )

    assert "localStorage" not in source
    assert "sessionStorage" not in source
    assert "indexedDB" not in source


def test_frontend_exposes_distinct_strategy_workflow_destinations() -> None:
    app = (FRONTEND / "App.tsx").read_text(encoding="utf-8")
    pages = (FRONTEND / "components" / "WorkflowPages.tsx").read_text(encoding="utf-8")
    workflow_api = (FRONTEND / "workflowApi.ts").read_text(encoding="utf-8")
    types = (FRONTEND / "types.ts").read_text(encoding="utf-8")

    for label in (
        "الرئيسية",
        "الاستراتيجيات",
        "الفرص",
        "الاختبار التاريخي",
        "التداول",
        "الأداء",
    ):
        assert label in app
    assert 'setCurrentView("performance")' in app
    assert 'setCurrentView("opportunities")' in app
    assert 'setCurrentView("backtesting")' in app
    assert "WorkflowHomePanel" in app
    assert "SetupReviewPage" in app
    assert "current_price" in pages + types
    assert "price_observed_at" in pages + types
    assert "price_state" in pages + types
    assert "StrategyConfigurationFields" in pages
    assert "إنشاء البوت" in pages
    assert "نتائج الاختبارات التاريخية لا تختلط" in pages
    assert "/v1/strategy-templates" in workflow_api
    assert "/v1/strategy-setups" in workflow_api
    assert "/v1/opportunities" in workflow_api
    assert "/v1/bot-deployments" in workflow_api
    assert "localStorage" not in workflow_api + pages


def test_frontend_uses_english_digits_in_the_arabic_interface() -> None:
    source = "\n".join(
        path.read_text(encoding="utf-8")
        for path in FRONTEND.rglob("*")
        if path.is_file() and path.suffix in {".ts", ".tsx"}
    )
    formatter = (FRONTEND / "lib" / "format.ts").read_text(encoding="utf-8")

    forbidden_digits = "".join(chr(code) for code in range(0x0660, 0x066A))
    forbidden_digits += "".join(chr(code) for code in range(0x06F0, 0x06FA))

    assert not any(digit in source for digit in forbidden_digits)
    assert '"ar-SA-u-nu-latn"' in formatter
    assert 'numberingSystem: "latn"' in formatter
