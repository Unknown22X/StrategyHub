from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
FRONTEND = ROOT / "frontend" / "src"


def _read(relative: str) -> str:
    return (FRONTEND / relative).read_text(encoding="utf-8")


def test_discovery_frontend_uses_only_rangebot_local_api_boundary() -> None:
    api = _read("api.ts")
    page = _read("components/DiscoveryLabPage.tsx")

    for endpoint in (
        '"/v1/discovery/scans"',
        '"/v1/backtests"',
        '}/trades`',
        '}/equity`',
        '}/create-strategy`',
    ):
        assert endpoint in api

    combined = f"{api}\n{page}".lower()
    assert "api.gateio" not in combined
    assert "gate.com/api" not in combined
    assert "tradingview" not in combined
    assert "coingecko" not in combined
    assert "coinmarketcap" not in combined
    assert "localstorage" not in combined
    assert "sessionstorage" not in combined


def test_discovery_page_is_dynamic_evidence_first_and_non_executing() -> None:
    page = _read("components/DiscoveryLabPage.tsx")
    types = _read("types.ts")

    assert "supports_scanning" in types
    assert "supports_backtesting" in types
    assert "candidate_metrics" in types
    assert "StrategyConfigurationFields" in page
    assert "metadata.candidate_metrics.map" in page
    assert "لا يرسل المختبر أوامر" in page
    assert "ليست توقعاً للربح ولا توصية تداول" in page
    assert "تحذيرات وافتراضات" in page
    assert "الرسوم" in page
    assert "التمويل" in page
    assert "أقصى تراجع" in page
    assert "منحنى الرصيد المحاكى" in page
    assert "إنشاء استراتيجية متوقفة" in page
    assert "أبحاث محفوظة" in page
    assert "listDiscoveryScans" in page
    assert "listBacktests" in page
    assert "transitionStrategy" not in page
    assert "submitManualOrder" not in page


def test_discovery_navigation_exists_globally_and_on_supported_strategy_pages() -> None:
    app = _read("App.tsx")
    detail = _read("components/StrategyDetailPage.tsx")

    assert '| "opportunities"' in app
    assert '| "backtesting"' in app
    assert "الفرص" in app
    assert "الاختبار التاريخي" in app
    assert "<OpportunitiesPage" in app
    assert "<BacktestingPage" in app
    assert "<DiscoveryLabPage" in app
    assert "فحص السوق واختبار العملات" in detail
    assert "metadata?.supports_scanning && metadata.supports_backtesting" in detail


def test_discovery_styles_are_rtl_responsive_and_avoid_decorative_gradients() -> None:
    styles = _read("styles.css")

    assert ".discovery-stage" in styles
    assert ".candidate-workspace" in styles
    assert ".backtest-report" in styles
    assert ".assessment-banner" in styles
    assert "@media (max-width: 900px)" in styles
    assert "@media (max-width: 640px)" in styles
    discovery_styles = styles[styles.index("/* Discovery Lab */") :]
    assert "linear-gradient" not in discovery_styles
    assert "radial-gradient" not in discovery_styles
