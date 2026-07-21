import { useEffect, useMemo, useRef, useState } from "react";
import type { ReactNode } from "react";

import {
  cancelPaperPendingEntry,
  loadAccountPerformance,
  loadStrategyDecisions,
  saveApplicationSettings,
  switchRuntimeEnvironment,
  transitionStrategy,
} from "./api";
import { DashboardCustomizeDrawer } from "./components/DashboardCustomizeDrawer";
import { DashboardFilterBar } from "./components/DashboardFilterBar";
import { DiscoveryLabPage } from "./components/DiscoveryLabPage";
import { EnvironmentSelector } from "./components/EnvironmentSelector";
import { GateConnectionDrawer } from "./components/GateConnectionDrawer";
import { Icon, type IconName } from "./components/Icon";
import { ManualTradeDrawer } from "./components/ManualTradeDrawer";
import { OperationsDrawer } from "./components/OperationsDrawer";
import { RiskManagementDrawer } from "./components/RiskManagementDrawer";
import { StrategyChart } from "./components/StrategyChart";
import { StrategyCreateDrawer } from "./components/StrategyCreateDrawer";
import { StrategyDetailPage } from "./components/StrategyDetailPage";
import { TradeHistoryPage } from "./components/TradeHistoryPage";
import {
  BacktestingPage,
  BotTradingPage,
  OpportunitiesPage,
  PerformancePage,
  SetupReviewPage,
  StrategiesPage,
  WorkflowHomePanel,
} from "./components/WorkflowPages";
import { EmptyState, StateView, StatusPill } from "./components/StateView";
import {
  defaultDashboardFilters,
  normalizeDashboardFilters,
  serializeDashboardFilters,
  type DashboardFilters,
} from "./dashboardFilters";
import {
  defaultDashboardLayout,
  normalizeDashboardLayout,
  serializeDashboardLayout,
  type DashboardLayoutSettings,
  type DashboardWidgetId,
} from "./dashboardLayout";
import { useDashboard } from "./hooks/useDashboard";
import {
  directionLabel,
  formatDateTime,
  formatDecimal,
  formatMoney,
  formatPercent,
  strategyStatusLabel,
} from "./lib/format";
import type {
  AccountPerformanceSeries,
  ActivityEvent,
  Environment,
  EnvironmentRuntimeState,
  ExchangeOpenOrderSnapshot,
  ExchangePositionSnapshot,
  JsonValue,
  ModeState,
  PaperPosition,
  PrivateStreamState,
  RemoteData,
  StrategyDecision,
  StrategyInstance,
  StrategyOverviewItem,
  StrategyTypeMetadata,
} from "./types";

const environmentLabels: Record<Environment, string> = {
  live: "LIVE",
  testnet: "Testnet",
  paper: "Paper",
};

const initialDecisions: RemoteData<StrategyDecision[]> = { status: "loading" };
type AppView =
  | "dashboard"
  | "strategies"
  | "setup"
  | "opportunities"
  | "backtesting"
  | "trading"
  | "performance"
  | "strategy"
  | "discovery"
  | "trades";

export default function App() {
  const { bundle, refresh, refreshing } = useDashboard();
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [selectedStrategyId, setSelectedStrategyId] = useState<string | null>(null);
  const [selectedSetupId, setSelectedSetupId] = useState<string | null>(null);
  const [discoveryStrategyId, setDiscoveryStrategyId] = useState<string | null>(null);
  const [currentView, setCurrentView] = useState<AppView>("dashboard");
  const [manualTradeOpen, setManualTradeOpen] = useState(false);
  const [operationsOpen, setOperationsOpen] = useState(false);
  const [riskManagementOpen, setRiskManagementOpen] = useState(false);
  const [connectionOpen, setConnectionOpen] = useState(false);
  const [dashboardCustomizeOpen, setDashboardCustomizeOpen] = useState(false);
  const [strategyCreateOpen, setStrategyCreateOpen] = useState(false);
  const [strategyCreateTypeId, setStrategyCreateTypeId] = useState<string | null>(null);
  const [dashboardLayout, setDashboardLayout] = useState<DashboardLayoutSettings>(defaultDashboardLayout);
  const [dashboardFilters, setDashboardFilters] = useState<DashboardFilters>(defaultDashboardFilters);
  const [decisions, setDecisions] = useState<RemoteData<StrategyDecision[]>>(initialDecisions);
  const [actionError, setActionError] = useState<string | null>(null);
  const [actionBusy, setActionBusy] = useState<string | null>(null);
  const sidebarInitialized = useRef(false);
  const dashboardLayoutInitialized = useRef(false);
  const dashboardFiltersInitialized = useRef(false);

  const settings = readyData(bundle.settings);
  const runtimeState = readyData(bundle.runtime);
  const runtimeEnvironment = runtimeState?.environment ?? null;
  const strategies = readyData(bundle.strategies) ?? [];
  const strategyOverview = readyData(bundle.strategyOverview) ?? [];
  const strategyTypes = readyData(bundle.strategyTypes) ?? [];
  const environment = runtimeEnvironment?.active_engine_environment ?? null;
  const environmentOperational = runtimeEnvironment?.transition_state === "ready"
    && runtimeEnvironment.activated;
  const modeState = environment === "live"
    ? readyData(bundle.liveState)
    : environment === "testnet"
      ? readyData(bundle.testnetState)
      : null;

  const activeStrategy = useMemo(() => {
    const selected = strategies.find((item) => item.instance_id === selectedStrategyId);
    return selected
      ?? strategies.find((item) => item.status === "running")
      ?? strategies.find((item) => item.status === "monitoring")
      ?? strategies[0]
      ?? null;
  }, [selectedStrategyId, strategies]);

  const strategyMetadata = useMemo(
    () => strategyTypes.find((item) => item.type_id === activeStrategy?.type_id) ?? null,
    [activeStrategy, strategyTypes],
  );
  const discoveryInitialStrategy = useMemo(
    () => strategies.find((item) => item.instance_id === discoveryStrategyId) ?? null,
    [discoveryStrategyId, strategies],
  );

  const displayEnvironment = dashboardFilters.environment === "current"
    ? environment
    : dashboardFilters.environment;
  const displayModeState = displayEnvironment === "live"
    ? readyData(bundle.liveState)
    : displayEnvironment === "testnet"
      ? readyData(bundle.testnetState)
      : null;
  const filteredStrategies = useMemo(
    () => strategies.filter((strategy) => (
      (!dashboardFilters.strategyId || strategy.instance_id === dashboardFilters.strategyId)
      && (!dashboardFilters.symbol || strategy.symbol === dashboardFilters.symbol)
      && (!displayEnvironment || strategy.environment === displayEnvironment)
    )),
    [dashboardFilters.strategyId, dashboardFilters.symbol, displayEnvironment, strategies],
  );
  const filteredStrategyOverview = useMemo(
    () => strategyOverview.filter((strategy) => (
      (!dashboardFilters.strategyId || strategy.instance_id === dashboardFilters.strategyId)
      && (!dashboardFilters.symbol || strategy.symbol === dashboardFilters.symbol)
      && (!displayEnvironment || strategy.environment === displayEnvironment)
    )),
    [dashboardFilters.strategyId, dashboardFilters.symbol, displayEnvironment, strategyOverview],
  );
  const dashboardActiveStrategy = useMemo(
    () => filteredStrategies.find((item) => item.status === "running")
      ?? filteredStrategies.find((item) => item.status === "monitoring")
      ?? filteredStrategies[0]
      ?? null,
    [filteredStrategies],
  );
  const dashboardStrategyMetadata = useMemo(
    () => strategyTypes.find((item) => item.type_id === dashboardActiveStrategy?.type_id) ?? null,
    [dashboardActiveStrategy, strategyTypes],
  );
  const dashboardSymbols = useMemo(() => {
    const symbols = new Set<string>();
    for (const strategy of strategies) symbols.add(strategy.symbol);
    for (const item of readyData(bundle.watchlist)?.items ?? []) symbols.add(item.symbol);
    for (const state of [readyData(bundle.liveState), readyData(bundle.testnetState)]) {
      for (const position of state?.snapshot?.positions ?? []) symbols.add(position.contract);
      for (const order of state?.snapshot?.open_orders ?? []) symbols.add(order.contract);
    }
    return [...symbols].sort();
  }, [bundle.liveState, bundle.testnetState, bundle.watchlist, strategies]);

  useEffect(() => {
    if (!sidebarInitialized.current && settings) {
      setSidebarCollapsed(settings.sidebar_preferences.collapsed === true);
      sidebarInitialized.current = true;
    }
    if (!dashboardLayoutInitialized.current && settings) {
      setDashboardLayout(normalizeDashboardLayout(settings.dashboard_layout));
      dashboardLayoutInitialized.current = true;
    }
    if (!dashboardFiltersInitialized.current && settings) {
      setDashboardFilters(normalizeDashboardFilters(settings.dashboard_filters));
      dashboardFiltersInitialized.current = true;
    }
  }, [settings]);

  useEffect(() => {
    if (!dashboardActiveStrategy) {
      setDecisions({ status: "ready", data: [] });
      return;
    }
    const controller = new AbortController();
    setDecisions({ status: "loading" });
    loadStrategyDecisions(dashboardActiveStrategy.instance_id, controller.signal)
      .then((data) => setDecisions({ status: "ready", data }))
      .catch((error) => {
        if (!(error instanceof DOMException && error.name === "AbortError")) {
          setDecisions({
            status: "error",
            message: error instanceof Error ? error.message : "تعذر تحميل القرارات.",
          });
        }
      });
    return () => controller.abort();
  }, [dashboardActiveStrategy?.instance_id]);

  async function saveDashboardLayout(next: DashboardLayoutSettings) {
    if (!settings) {
      throw new Error("إعدادات المحرك غير متاحة حالياً.");
    }
    const saved = await saveApplicationSettings({
      environment: settings.environment,
      ui_language: settings.ui_language,
      dashboard_layout: serializeDashboardLayout(next),
      dashboard_filters: settings.dashboard_filters,
      sidebar_preferences: settings.sidebar_preferences,
      application_preferences: settings.application_preferences,
    });
    setDashboardLayout(normalizeDashboardLayout(saved.dashboard_layout));
    await refresh();
  }

  async function saveDashboardFilters(next: DashboardFilters) {
    if (!settings) {
      throw new Error("إعدادات المحرك غير متاحة حالياً.");
    }
    const saved = await saveApplicationSettings({
      environment: settings.environment,
      ui_language: settings.ui_language,
      dashboard_layout: settings.dashboard_layout,
      dashboard_filters: serializeDashboardFilters(next),
      sidebar_preferences: settings.sidebar_preferences,
      application_preferences: settings.application_preferences,
    });
    setDashboardFilters(normalizeDashboardFilters(saved.dashboard_filters));
    await refresh();
  }

  async function toggleSidebar() {
    const next = !sidebarCollapsed;
    setSidebarCollapsed(next);
    if (!settings) {
      return;
    }
    try {
      await saveApplicationSettings({
        environment: settings.environment,
        ui_language: settings.ui_language,
        dashboard_layout: settings.dashboard_layout,
        dashboard_filters: settings.dashboard_filters,
        sidebar_preferences: {
          ...settings.sidebar_preferences,
          collapsed: next,
        },
        application_preferences: settings.application_preferences,
      });
      await refresh();
    } catch (error) {
      setActionError(error instanceof Error ? error.message : "تعذر حفظ وضع القائمة.");
    }
  }

  async function handleEnvironmentSwitch(next: Environment) {
    let confirmation = "";
    if (next === "live") {
      const accepted = window.confirm(
        "تفعيل LIVE سيستخدم أموال Gate.io الحقيقية بعد اجتياز فحوص الأمان. هل تريد المتابعة؟",
      );
      if (!accepted) return;
      confirmation = "SWITCH TO LIVE";
    }
    setActionBusy("environment-switch");
    setActionError(null);
    try {
      await switchRuntimeEnvironment(next, confirmation);
      setManualTradeOpen(false);
      setStrategyCreateOpen(false);
      await refresh();
    } catch (error) {
      setActionError(error instanceof Error ? error.message : "تعذر تبديل بيئة التداول.");
      await refresh();
    } finally {
      setActionBusy(null);
    }
  }

  function openManualTrade() {
    if (!environment || !environmentOperational) {
      setActionError(
        runtimeEnvironment?.message_ar
          ?? "بيئة المحرك غير جاهزة. أكمل تبديل البيئة قبل فتح التداول اليدوي.",
      );
      return;
    }
    setManualTradeOpen(true);
  }

  function openStrategyCreate(typeId: string | null = null) {
    if (!environment || !environmentOperational) {
      setActionError(
        runtimeEnvironment?.message_ar
          ?? "بيئة المحرك غير جاهزة. أكمل تبديل البيئة قبل إنشاء Strategy Instance.",
      );
      return;
    }
    setStrategyCreateTypeId(typeId);
    setStrategyCreateOpen(true);
  }

  function openStrategyPage(instanceId: string) {
    setSelectedStrategyId(instanceId);
    setCurrentView("strategy");
  }

  function openDiscoveryLab(instanceId: string | null = null) {
    setDiscoveryStrategyId(instanceId);
    setCurrentView("discovery");
  }

  async function handleStrategyChanged(strategy: StrategyInstance) {
    setSelectedStrategyId(strategy.instance_id);
    await refresh();
  }

  async function handleStrategyDeleted(instanceId: string) {
    if (selectedStrategyId === instanceId) {
      setSelectedStrategyId(null);
    }
    setCurrentView("dashboard");
    await refresh();
  }

  async function runStrategyAction(
    strategy: StrategyInstance,
    action: "start" | "monitor" | "pause" | "stop",
  ) {
    setActionBusy(`${strategy.instance_id}:${action}`);
    setActionError(null);
    try {
      await transitionStrategy(strategy.instance_id, action);
      await refresh();
    } catch (error) {
      setActionError(error instanceof Error ? error.message : "تعذر تحديث الاستراتيجية.");
    } finally {
      setActionBusy(null);
    }
  }

  const dashboardWidgets: Record<DashboardWidgetId, ReactNode> = {
    summary: (
      <SummaryCards
        environment={displayEnvironment}
        modeState={displayModeState}
        bundle={bundle}
        activeStrategy={dashboardActiveStrategy}
      />
    ),
    active: (
      <section className="dashboard-grid primary-grid">
        <ActiveStrategyPanel
          strategy={dashboardActiveStrategy}
          metadata={dashboardStrategyMetadata}
          decisions={decisions}
          onAdd={openStrategyCreate}
        />
        <PositionPanel environment={displayEnvironment} modeState={displayModeState} bundle={bundle} />
      </section>
    ),
    strategiesRisk: (
      <section className="dashboard-grid secondary-grid">
        <StrategiesOverview
          strategies={filteredStrategyOverview}
          metadata={strategyTypes}
          busy={actionBusy}
          onSelect={openStrategyPage}
          onAction={runStrategyAction}
        />
        <RiskPanel environment={displayEnvironment} modeState={displayModeState} bundle={bundle} />
      </section>
    ),
    marketAlerts: (
      <section className="dashboard-grid secondary-grid">
        <WatchlistPanel bundle={bundle} symbolFilter={dashboardFilters.symbol} />
        <AlertsPanel
          environment={displayEnvironment}
          modeState={displayModeState}
          strategies={filteredStrategies}
          runtime={bundle.runtime}
        />
      </section>
    ),
    orders: (
      <OrdersPanel
        environment={displayEnvironment}
        modeState={displayModeState}
        bundle={bundle}
        symbolFilter={dashboardFilters.symbol}
        onChanged={() => void refresh()}
      />
    ),
    performance: (
      <PerformancePanel
        environment={displayEnvironment}
        modeState={displayModeState}
        period={dashboardFilters.period}
      />
    ),
    activity: (
      <RecentActivity
        activity={bundle.activity}
        eventType={dashboardFilters.eventType}
        period={dashboardFilters.period}
        environment={displayEnvironment}
        strategyId={dashboardFilters.strategyId}
        symbol={dashboardFilters.symbol}
      />
    ),
  };

  return (
    <div className={sidebarCollapsed ? "app-shell sidebar-collapsed" : "app-shell"}>
      <Sidebar
        collapsed={sidebarCollapsed}
        currentView={currentView}
        onOpenConnection={() => setConnectionOpen(true)}
        onOpenDashboard={() => setCurrentView("dashboard")}
        onOpenStrategies={() => setCurrentView("strategies")}
        onOpenOpportunities={() => setCurrentView("opportunities")}
        onOpenBacktesting={() => setCurrentView("backtesting")}
        onOpenTrading={() => setCurrentView("trading")}
        onOpenPerformance={() => setCurrentView("performance")}
        onOpenOperations={() => setOperationsOpen(true)}
        onOpenRiskManagement={() => setRiskManagementOpen(true)}
        onOpenTrades={() => setCurrentView("trades")}
        onToggle={toggleSidebar}
      />

      <main className="main-content">
        <TopStatusBar
          environment={environment}
          environmentRuntime={runtimeEnvironment}
          environmentBusy={actionBusy === "environment-switch"}
          modeState={modeState}
          privateStream={bundle.privateStream}
          activeStrategy={activeStrategy}
          runtime={bundle.runtime}
          loadedAt={bundle.loadedAt}
          refreshing={refreshing}
          onRefresh={() => void refresh()}
          onOpenTrade={openManualTrade}
          onSwitchEnvironment={(next) => void handleEnvironmentSwitch(next)}
        />

        {actionError && (
          <div className="global-alert-wrap">
            <div className="inline-alert error-alert" role="alert">
              <Icon name="alert" />
              <span>{actionError}</span>
              <button type="button" onClick={() => setActionError(null)} aria-label="إخفاء الخطأ">
                <Icon name="x" size={16} />
              </button>
            </div>
          </div>
        )}

        {currentView === "strategies" ? (
          <StrategiesPage
            strategyTypes={strategyTypes}
            onOpenSetup={(setupId) => {
              setSelectedSetupId(setupId);
              setCurrentView("setup");
            }}
          />
        ) : currentView === "setup" && selectedSetupId && environment ? (
          <SetupReviewPage
            setupId={selectedSetupId}
            environment={environment}
            strategyTypes={strategyTypes}
            onBack={() => setCurrentView("strategies")}
            onOpenBacktesting={() => setCurrentView("backtesting")}
            onOpenTrading={() => setCurrentView("trading")}
          />
        ) : currentView === "opportunities" ? (
          <OpportunitiesPage
            strategyTypes={strategyTypes}
            onOpenSetup={(setupId) => {
              setSelectedSetupId(setupId);
              setCurrentView("setup");
            }}
          />
        ) : currentView === "backtesting" ? (
          <BacktestingPage
            initialSetupId={selectedSetupId}
            onOpenSetup={(setupId) => {
              setSelectedSetupId(setupId);
              setCurrentView("setup");
            }}
          />
        ) : currentView === "trading" ? (
          <BotTradingPage />
        ) : currentView === "performance" && environment ? (
          <PerformancePage environment={environment} />
        ) : currentView === "trades" ? (
          <TradeHistoryPage
            currentEnvironment={environment}
            strategies={strategies}
            onBack={() => setCurrentView("dashboard")}
          />
        ) : currentView === "discovery" ? (
          <DiscoveryLabPage
            strategyTypes={strategyTypes}
            environment={environment}
            initialStrategy={discoveryInitialStrategy}
            onBack={() => setCurrentView("dashboard")}
            onStrategyCreated={(strategy) => {
              setSelectedStrategyId(strategy.instance_id);
              setCurrentView("strategy");
              void refresh();
            }}
          />
        ) : currentView === "strategy" && activeStrategy ? (
          <StrategyDetailPage
            strategy={activeStrategy}
            metadata={strategyMetadata}
            onBack={() => setCurrentView("dashboard")}
            onOpenDiscovery={() => openDiscoveryLab(activeStrategy.instance_id)}
            onChanged={(strategy) => void handleStrategyChanged(strategy)}
            onDeleted={(instanceId) => void handleStrategyDeleted(instanceId)}
          />
        ) : (
          <div className="dashboard-content">
            <header className="page-heading">
              <div>
                <span className="eyebrow">مركز العمليات واتخاذ القرار</span>
                <h1>لوحة RangeBot</h1>
                <p>حالة المحرك والحساب والاستراتيجيات والمخاطر من مصادرها الحقيقية.</p>
              </div>
              <div className="heading-actions">
                <button className="secondary-button" type="button" onClick={() => setDashboardCustomizeOpen(true)}>
                  <Icon name="settings" />
                  تخصيص اللوحة
                </button>
                <button className="secondary-button" type="button" onClick={openManualTrade}>
                  <Icon name="trade" />
                  فتح التداول اليدوي
                </button>
                <button className="secondary-button" type="button" onClick={() => setCurrentView("opportunities")}>
                  <Icon name="activity" />
                  الفرص
                </button>
                <button className="primary-button" type="button" onClick={() => setCurrentView("strategies")}>
                  <Icon name="plus" />
                  إنشاء استراتيجية
                </button>
              </div>
            </header>

            <WorkflowHomePanel
              onOpenStrategies={() => setCurrentView("strategies")}
              onOpenOpportunities={() => setCurrentView("opportunities")}
              onOpenBacktesting={() => setCurrentView("backtesting")}
            />

            <DashboardFilterBar
              filters={dashboardFilters}
              currentEnvironment={environment}
              strategies={strategies}
              symbols={dashboardSymbols}
              onSave={saveDashboardFilters}
            />

            <div className={`dashboard-widgets density-${dashboardLayout.density}`}>
              {dashboardLayout.order
                .filter((widget) => !dashboardLayout.hidden.includes(widget))
                .map((widget) => (
                  <div className={`dashboard-widget dashboard-widget-${widget}`} key={widget}>
                    {dashboardWidgets[widget]}
                  </div>
                ))}
            </div>
          </div>
        )}
      </main>

      {environment && (
        <>
          <ManualTradeDrawer
            open={manualTradeOpen}
            environment={environment}
            environmentRuntime={runtimeEnvironment}
            defaultSymbol={activeStrategy?.symbol ?? readyData(bundle.watchlist)?.items.find((item) => item.is_active)?.symbol ?? "BTC_USDT"}
            onClose={() => setManualTradeOpen(false)}
            onSubmitted={() => void refresh()}
          />
          <StrategyCreateDrawer
            open={strategyCreateOpen}
            environment={environment}
            initialTypeId={strategyCreateTypeId}
            strategyTypes={strategyTypes}
            onClose={() => {
              setStrategyCreateOpen(false);
              setStrategyCreateTypeId(null);
            }}
            onCreated={(strategy) => {
              setSelectedStrategyId(strategy.instance_id);
              setCurrentView("strategy");
              void refresh();
            }}
          />
        </>
      )}
      <OperationsDrawer
        open={operationsOpen}
        onClose={() => setOperationsOpen(false)}
        onRestored={() => void refresh()}
      />
      <RiskManagementDrawer
        open={riskManagementOpen}
        onClose={() => setRiskManagementOpen(false)}
        onSaved={() => void refresh()}
      />
      <GateConnectionDrawer
        open={connectionOpen}
        initialMode={environment === "testnet" ? "testnet" : "live"}
        onClose={() => setConnectionOpen(false)}
        onChanged={() => void refresh()}
      />
      <DashboardCustomizeDrawer
        open={dashboardCustomizeOpen}
        layout={dashboardLayout}
        onClose={() => setDashboardCustomizeOpen(false)}
        onSave={saveDashboardLayout}
      />
    </div>
  );
}

interface SidebarProps {
  collapsed: boolean;
  currentView: AppView;
  onOpenConnection: () => void;
  onOpenDashboard: () => void;
  onOpenStrategies: () => void;
  onOpenOpportunities: () => void;
  onOpenBacktesting: () => void;
  onOpenTrading: () => void;
  onOpenPerformance: () => void;
  onOpenOperations: () => void;
  onOpenRiskManagement: () => void;
  onOpenTrades: () => void;
  onToggle: () => void;
}

function Sidebar({
  collapsed,
  currentView,
  onOpenConnection,
  onOpenDashboard,
  onOpenStrategies,
  onOpenOpportunities,
  onOpenBacktesting,
  onOpenTrading,
  onOpenPerformance,
  onOpenOperations,
  onOpenRiskManagement,
  onOpenTrades,
  onToggle,
}: SidebarProps) {
  return (
    <aside className="sidebar" aria-label="التنقل الرئيسي">
      <div className="brand-row">
        <div className="brand-mark">R</div>
        {!collapsed && (
          <div className="brand-copy">
            <strong>RangeBot</strong>
            <span>Trading Operations</span>
          </div>
        )}
        <button className="icon-button sidebar-toggle" type="button" onClick={onToggle} aria-label="طي القائمة">
          <Icon name={collapsed ? "menu" : "chevron"} />
        </button>
      </div>

      <nav className="sidebar-nav">
        <SidebarLink icon="grid" label="الرئيسية" active={currentView === "dashboard"} collapsed={collapsed} onClick={onOpenDashboard} />
        <SidebarLink icon="strategy" label="الاستراتيجيات" active={["strategies", "setup"].includes(currentView)} collapsed={collapsed} onClick={onOpenStrategies} />
        <SidebarLink icon="activity" label="الفرص" active={currentView === "opportunities"} collapsed={collapsed} onClick={onOpenOpportunities} />
        <SidebarLink icon="chart" label="الاختبار التاريخي" active={currentView === "backtesting"} collapsed={collapsed} onClick={onOpenBacktesting} />
        <SidebarLink icon="trade" label="التداول" active={currentView === "trading"} collapsed={collapsed} onClick={onOpenTrading} />
        <SidebarLink icon="chart" label="الأداء" active={currentView === "performance"} collapsed={collapsed} onClick={onOpenPerformance} />
      </nav>

      <div className="sidebar-section">
        {!collapsed && <span className="sidebar-section-title">أدوات التشغيل</span>}
        <SidebarLink icon="shield" label="المخاطر والحماية" collapsed={collapsed} onClick={onOpenRiskManagement} />
        <SidebarLink icon="trade" label="سجل التنفيذات" active={currentView === "trades"} collapsed={collapsed} onClick={onOpenTrades} />
      </div>

      <div className="sidebar-footer">
        <SidebarLink
          icon="archive"
          label="النسخ الاحتياطية والسجلات"
          collapsed={collapsed}
          onClick={onOpenOperations}
        />
        <SidebarLink
          icon="settings"
          label="اتصال Gate.io والإعدادات"
          collapsed={collapsed}
          onClick={onOpenConnection}
        />
        {!collapsed && (
          <div className="source-note">
            <span className="source-dot" />
            الواجهة متصلة بـ localhost فقط
          </div>
        )}
      </div>
    </aside>
  );
}

function SidebarLink({
  icon,
  label,
  active = false,
  collapsed,
  onClick,
}: {
  icon: IconName;
  label: string;
  active?: boolean;
  collapsed: boolean;
  onClick?: () => void;
}) {
  return (
    <button
      className={active ? "sidebar-link active" : "sidebar-link"}
      type="button"
      title={label}
      onClick={onClick}
    >
      <Icon name={icon} />
      {!collapsed && <span>{label}</span>}
    </button>
  );
}

interface TopStatusBarProps {
  environment: Environment | null;
  environmentRuntime: EnvironmentRuntimeState | null;
  environmentBusy: boolean;
  modeState: ModeState | null;
  privateStream: RemoteData<PrivateStreamState>;
  activeStrategy: StrategyInstance | null;
  runtime: RemoteData<{ lifecycle: string; last_heartbeat_at: string }>;
  loadedAt: string;
  refreshing: boolean;
  onRefresh: () => void;
  onOpenTrade: () => void;
  onSwitchEnvironment: (environment: Environment) => void;
}

function TopStatusBar({
  environment,
  environmentRuntime,
  environmentBusy,
  modeState,
  privateStream,
  activeStrategy,
  runtime,
  loadedAt,
  refreshing,
  onRefresh,
  onOpenTrade,
  onSwitchEnvironment,
}: TopStatusBarProps) {
  const snapshot = modeState?.snapshot;
  const environmentReady = environmentRuntime?.transition_state === "ready"
    && environmentRuntime.activated;
  return (
    <header className="top-status-bar">
      <div className="top-status-primary">
        <EnvironmentSelector
          runtime={environmentRuntime}
          busy={environmentBusy}
          onChange={onSwitchEnvironment}
        />
        <StateView value={runtime} compact>
          {(state) => (
            <StatusPill
              label={state.lifecycle === "running" ? "المحرك متصل" : state.lifecycle}
              tone={state.lifecycle === "running" ? "positive" : "negative"}
              pulse={state.lifecycle === "running"}
            />
          )}
        </StateView>
        {environment !== null && environment !== "paper" && (
          <>
            <StatusPill
              label={snapshot?.rest_snapshot_confirmed ? "Gate REST متصل" : "Gate REST غير جاهز"}
              tone={snapshot?.rest_snapshot_confirmed ? "positive" : "warning"}
            />
            <StatusPill
              label={snapshot?.subscription_confirmed ? "سوق WebSocket متصل" : "سوق WebSocket غير جاهز"}
              tone={snapshot?.subscription_confirmed ? "positive" : "warning"}
            />
            <StateView value={privateStream} compact unavailableLabel="الحساب الخاص غير متاح">
              {(state) => <PrivateStreamPill state={state} />}
            </StateView>
            <StatusPill
              label={snapshot?.market_ready ? "البيانات حديثة" : "البيانات غير مؤكدة"}
              tone={snapshot?.market_ready ? "positive" : "warning"}
            />
          </>
        )}
      </div>
      <div className="top-status-secondary">
        <span className="status-text">
          النشط: <strong>{activeStrategy?.name ?? "لا توجد استراتيجية نشطة"}</strong>
        </span>
        <span className="status-text">
          آخر مزامنة: <strong>{formatDateTime(snapshot?.reconciled_at ?? loadedAt)}</strong>
        </span>
        {modeState?.emergency_stop && (
          <StatusPill label="إيقاف الطوارئ مفعّل" tone="negative" pulse />
        )}
        <button
          className="top-action-button"
          type="button"
          disabled={!environmentReady}
          title={environmentReady ? "فتح التداول اليدوي" : "أكمل تبديل البيئة أولاً"}
          onClick={onOpenTrade}
        >
          <Icon name="trade" size={16} />
          تداول يدوي
        </button>
        <button className="icon-button" type="button" onClick={onRefresh} aria-label="تحديث البيانات">
          <Icon className={refreshing ? "spin" : ""} name="refresh" />
        </button>
      </div>
    </header>
  );
}

function PrivateStreamPill({ state }: { state: PrivateStreamState }) {
  const presentation = {
    connected: { label: "الحساب الخاص متصل", tone: "positive" as const, pulse: true },
    reconciling: { label: "الحساب الخاص يصالح", tone: "warning" as const, pulse: true },
    connecting: { label: "الحساب الخاص يتصل", tone: "warning" as const, pulse: true },
    reconnecting: { label: "الحساب الخاص يعيد الاتصال", tone: "warning" as const, pulse: true },
    credentials_missing: { label: "اعتمادات الحساب مفقودة", tone: "warning" as const, pulse: false },
    error: { label: "خطأ في الحساب الخاص", tone: "negative" as const, pulse: false },
    disabled: { label: "الحساب الخاص معطّل", tone: "neutral" as const, pulse: false },
  }[state.status];
  return (
    <StatusPill
      label={presentation.label}
      tone={presentation.tone}
      pulse={presentation.pulse}
    />
  );
}

function SummaryCards({
  environment,
  modeState,
  bundle,
  activeStrategy,
}: {
  environment: Environment | null;
  modeState: ModeState | null;
  bundle: ReturnType<typeof useDashboard>["bundle"];
  activeStrategy: StrategyInstance | null;
}) {
  const paperAccount = readyData(bundle.paperAccount);
  const paperPerformance = readyData(bundle.paperPerformance);
  const latestPaperPoint = paperPerformance?.points.at(-1);
  const snapshot = modeState?.snapshot;
  const availableBalance = environment === "paper"
    ? paperAccount?.available_futures_balance
    : snapshot?.available_futures_balance;
  const positionQuantity = environment === "paper"
    ? paperAccount?.position_quantity
    : snapshot?.position_quantity;
  const cards = [
    {
      label: "إجمالي حقوق العقود",
      value: environment === "paper"
        ? formatMoney(latestPaperPoint?.total_equity)
        : formatMoney(snapshot?.total_futures_equity),
      note: environment === "paper" ? "المصدر: دفتر Paper المحلي" : "المصدر: Gate.io reconciliation",
      icon: "wallet" as IconName,
    },
    { label: "الرصيد المتاح", value: formatMoney(availableBalance), note: `المصدر: ${environmentLabel(environment)}`, icon: "wallet" as IconName },
    {
      label: "P&L المحقق المتراكم",
      value: environment === "paper"
        ? formatMoney(paperAccount?.realized_pnl_total)
        : formatMoney(snapshot?.realized_pnl_total),
      note: environment === "paper" ? "المصدر: دفتر Paper المحلي" : "يشمل التدفقات المسجلة في Gate.io",
      icon: "chart" as IconName,
    },
    {
      label: "P&L غير المحقق",
      value: environment === "paper"
        ? formatMoney(latestPaperPoint?.unrealized_pnl)
        : formatMoney(snapshot?.unrealized_pnl),
      note: environment === "paper" ? "المصدر: دفتر Paper والقيمة السوقية" : "المصدر: Gate.io",
      icon: "activity" as IconName,
    },
    {
      label: "صافي P&L بعد الرسوم والتمويل",
      value: environment === "paper"
        ? formatMoney(latestPaperPoint?.net_pnl_total)
        : formatMoney(snapshot?.net_pnl_total),
      note: environment === "paper" ? "دفتر Paper المركزي" : "مصالحة Gate.io",
      icon: "chart" as IconName,
    },
    {
      label: "الهامش المستخدم",
      value: environment === "paper"
        ? formatMoney(latestPaperPoint?.used_margin)
        : formatMoney(snapshot?.used_margin),
      note: environment === "paper"
        ? `${formatPercent(latestPaperPoint?.margin_usage_percentage)} من الحقوق`
        : `${formatPercent(snapshot?.margin_usage_percentage)} من الحقوق`,
      icon: "shield" as IconName,
    },
    {
      label: "الأوامر المفتوحة",
      value: environment === "paper" ? (paperAccount?.pending_entry ? "1" : "0") : String(snapshot?.open_orders.length ?? 0),
      note: environment === "paper" ? "محرك المحاكاة المحلي" : "لقطة Gate.io المفتوحة",
      icon: "trade" as IconName,
    },
    { label: "الاستراتيجية النشطة", value: activeStrategy?.name ?? "لا توجد", note: activeStrategy ? strategyStatusLabel(activeStrategy.status) : "أضف أو ابدأ استراتيجية", icon: "strategy" as IconName },
    { label: "المراكز المفتوحة", value: environment === "paper" ? (positionQuantity && Number(positionQuantity) !== 0 ? "1" : "0") : String(snapshot?.positions.length ?? 0), note: positionQuantity && Number(positionQuantity) !== 0 ? `${formatDecimal(positionQuantity)} عقود` : "لا يوجد مركز مؤكد", icon: "trade" as IconName },
  ];

  return (
    <section className="summary-grid" aria-label="ملخص الحساب">
      {cards.map((card) => (
        <article className="summary-card" key={card.label}>
          <div className="summary-icon"><Icon name={card.icon} /></div>
          <div>
            <span>{card.label}</span>
            <strong dir="auto">{card.value}</strong>
            <small>{card.note}</small>
          </div>
        </article>
      ))}
    </section>
  );
}

function ActiveStrategyPanel({
  strategy,
  metadata,
  decisions,
  onAdd,
}: {
  strategy: StrategyInstance | null;
  metadata: StrategyTypeMetadata | null;
  decisions: RemoteData<StrategyDecision[]>;
  onAdd: () => void;
}) {
  const latestDecision = readyData(decisions)?.[0] ?? null;
  if (!strategy) {
    return (
      <section className="panel active-strategy-panel">
        <PanelHeader title="الاستراتيجية النشطة" eyebrow="القرار الحالي" icon="strategy" />
        <EmptyState
          title="لا توجد استراتيجية محفوظة"
          description="أنشئ استراتيجية لبدء المراقبة وشرح قرارات الدخول."
          action={<button className="primary-button" type="button" onClick={onAdd}><Icon name="plus" /> إضافة استراتيجية</button>}
        />
      </section>
    );
  }

  const fields = metadata?.live_analysis_fields ?? [];
  return (
    <section className="panel active-strategy-panel">
      <PanelHeader
        title={strategy.name}
        eyebrow={metadata?.display_name_ar ?? strategy.type_id}
        icon="strategy"
        trailing={<StatusPill label={strategyStatusLabel(strategy.status)} tone={strategyTone(strategy.status)} pulse={strategy.status === "running"} />}
      />

      <div className="strategy-summary-row">
        <InfoItem label="العقد" value={strategy.symbol} />
        <InfoItem label="الإطار" value={`${strategy.timeframe_minutes} دقيقة`} />
        <InfoItem label="الاتجاه" value={directionLabel(strategy.direction)} />
        <InfoItem label="البيئة" value={environmentLabels[strategy.environment]} />
        <InfoItem label="آخر نشاط" value={formatDateTime(strategy.updated_at)} />
      </div>

      <div className="strategy-decision-layout">
        <div className="decision-card">
          <span className="eyebrow">آخر قرار موثّق</span>
          <StateView value={decisions} unavailableLabel="تعذر تحميل قرارات الاستراتيجية">
            {(items) => items.length === 0 ? (
              <EmptyState title="لا توجد قرارات بعد" description="ستظهر هنا أسباب الدخول أو الانتظار بعد أول تقييم." />
            ) : (
              <>
                <div className="decision-heading">
                  <strong>{signalLabel(latestDecision?.signal)}</strong>
                  <StatusPill
                    label={latestDecision?.eligible ? "مؤهل للدخول" : "انتظار / محظور"}
                    tone={latestDecision?.eligible ? "positive" : "warning"}
                  />
                </div>
                <p>{stringValue(latestDecision?.analysis.explanation_ar) ?? "لا يوجد شرح نصي متاح."}</p>
                <div className="reason-chips">
                  {latestDecision?.reason_codes.map((reason) => <span key={reason}>{reason}</span>)}
                </div>
                <small>وقت القرار: {formatDateTime(latestDecision?.occurred_at)}</small>
              </>
            )}
          </StateView>
        </div>

        <div className="analysis-grid">
          {fields.length === 0 ? (
            <EmptyState title="لا توجد حقول تحليل مسجلة" description="ستحدد الاستراتيجية الحقول التي يحتاجها هذا العرض." />
          ) : fields.map((field) => (
            <div className="analysis-metric" key={field.key}>
              <span>{field.label_ar}</span>
              <strong dir="auto">{displayJsonValue(latestDecision?.analysis[field.key], field.unit)}</strong>
            </div>
          ))}
        </div>
      </div>

      <StrategyChart
        strategy={strategy}
        metadata={metadata}
        decision={latestDecision}
      />
    </section>
  );
}

function PositionPanel({
  environment,
  modeState,
  bundle,
}: {
  environment: Environment | null;
  modeState: ModeState | null;
  bundle: ReturnType<typeof useDashboard>["bundle"];
}) {
  const paperPosition = readyData(bundle.paperPosition);
  const snapshot = modeState?.snapshot;
  const livePosition = snapshot?.positions[0] ?? null;
  const hasLivePosition = Boolean(livePosition);
  const hasPosition = environment === "paper" ? Boolean(paperPosition) : hasLivePosition;

  return (
    <section className="panel position-panel">
      <PanelHeader title="المركز والحماية" eyebrow="التعرض الحالي" icon="shield" />
      {!hasPosition ? (
        <EmptyState title="لا يوجد مركز مفتوح مؤكد" description="سيظهر المركز هنا بعد المصالحة أو تنفيذ أمر مقبول." />
      ) : environment === "paper" && paperPosition ? (
        <>
          <div className="position-direction-row">
            <StatusPill label={directionLabel(paperPosition.direction)} tone={paperPosition.direction === "long" ? "positive" : "negative"} />
            <span>فُتح: {formatDateTime(paperPosition.opened_at)}</span>
          </div>
          <div className="detail-list">
            <InfoItem label="الكمية" value={formatDecimal(paperPosition.quantity)} />
            <InfoItem label="سعر الدخول" value={formatDecimal(paperPosition.entry_price)} />
            <InfoItem label="الرافعة" value={`${paperPosition.leverage}×`} />
            <InfoItem label="الهامش" value={formatMoney(paperPosition.allocated_margin)} />
            <InfoItem label="رسوم الدخول" value={formatMoney(paperPosition.entry_fee)} />
            <InfoItem label="Maker fee" value={formatPercent(paperPosition.maker_fee_rate)} />
            <InfoItem label="Taker fee" value={formatPercent(paperPosition.taker_fee_rate)} />
            <InfoItem label="العقد" value={paperPosition.symbol ?? "غير متاح"} />
            <InfoItem label="المالك / المصدر" value={paperPositionOwnerLabel(paperPosition)} />
            <InfoItem label="تسجيل الملكية" value={formatDateTime(paperPosition.ownership_created_at)} />
            <InfoItem label="وقف التتبع الحالي" value={formatDecimal(paperPosition.trailing_stop_price)} />
            <InfoItem label="مسافة التتبع" value={formatDecimal(paperPosition.trailing_stop_distance)} />
            <InfoItem label="حالة التتبع" value={trailingStateLabel(paperPosition.trailing_state)} />
            <InfoItem label="تحذير التتبع" value={paperPosition.trailing_last_error ?? "لا يوجد"} />
          </div>
          <ProtectionState healthy={readyData(bundle.paperAccount)?.protection_state === "protected"} tp={null} sl={null} />
          <TrailingProtectionState
            state={paperPosition.trailing_state}
            orderId={paperPosition.trailing_order_id}
            warning={paperPosition.trailing_last_error}
          />
        </>
      ) : snapshot && livePosition ? (
        <>
          <div className="position-direction-row">
            <StatusPill label={livePosition.side === "long" ? "شراء / Long" : "بيع / Short"} tone={livePosition.side === "long" ? "positive" : "negative"} />
            <span>{livePosition.contract} · المصدر: Gate.io</span>
          </div>
          <div className="detail-list">
            <InfoItem label="الكمية" value={formatDecimal(livePosition.quantity)} />
            <InfoItem label="الرافعة" value={livePosition.leverage ? `${formatDecimal(livePosition.leverage)}×` : "غير متاح"} />
            <InfoItem label="سعر التصفية" value={formatDecimal(livePosition.liquidation_price)} />
            <InfoItem label="سعر الدخول" value={formatDecimal(livePosition.entry_price)} />
            <InfoItem label="Mark Price" value={formatDecimal(livePosition.mark_price)} />
            <InfoItem label="P&L غير المحقق" value={formatMoney(livePosition.unrealized_pnl)} />
            <InfoItem label="الهامش المخصص" value={formatMoney(livePosition.margin)} />
            <InfoItem label="قيمة المركز" value={formatMoney(livePosition.value)} />
            <InfoItem label="أوامر معلقة على المركز" value={String(livePosition.pending_orders)} />
            <InfoItem label="المالك / المصدر" value={positionOwnerLabel(livePosition)} />
            <InfoItem label="تسجيل الملكية" value={formatDateTime(livePosition.ownership_created_at)} />
            <InfoItem label="وقف التتبع الأولي" value={formatDecimal(livePosition.trailing_stop_price)} />
            <InfoItem label="مسافة التتبع" value={formatDecimal(livePosition.trailing_stop_distance)} />
            <InfoItem label="حالة التتبع" value={trailingStateLabel(livePosition.trailing_state)} />
            <InfoItem label="معرّف وقف التتبع" value={livePosition.trailing_order_id ?? "غير متاح"} />
            <InfoItem label="تحذير التتبع" value={livePosition.trailing_last_error ?? "لا يوجد"} />
            <InfoItem label="فُتح" value={formatDateTime(livePosition.opened_at)} />
          </div>
          <ProtectionState healthy={snapshot.protection_ready} tp={snapshot.tp_enabled} sl={snapshot.sl_enabled} />
          <TrailingProtectionState
            state={livePosition.trailing_state}
            orderId={livePosition.trailing_order_id}
            warning={livePosition.trailing_last_error}
          />
        </>
      ) : (
        <EmptyState title="المصالحة غير متاحة" description="لن يُعرض مركز قديم على أنه حالي." />
      )}
    </section>
  );
}

function ProtectionState({ healthy, tp, sl }: { healthy: boolean; tp: boolean | null; sl: boolean | null }) {
  return (
    <div className={healthy ? "protection-banner healthy" : "protection-banner danger"}>
      <Icon name={healthy ? "shield" : "alert"} />
      <div>
        <strong>{healthy ? "حماية TP/SL سليمة" : "مشكلة في حماية TP/SL"}</strong>
        <span>
          TP: {tp === null ? "غير متاح" : tp ? "نشط" : "متوقف"} · SL: {sl === null ? "غير متاح" : sl ? "نشط" : "متوقف"}
        </span>
      </div>
    </div>
  );
}

function TrailingProtectionState({
  state,
  orderId,
  warning,
}: {
  state: "desired" | "active" | "error" | null;
  orderId: string | null;
  warning: string | null;
}) {
  if (state === null) return null;
  const className = state === "active" ? "healthy" : state === "error" ? "danger" : "pending";
  return (
    <div className={`protection-banner ${className}`}>
      <Icon name={state === "error" ? "alert" : "shield"} />
      <div>
        <strong>وقف التتبع: {trailingStateLabel(state)}</strong>
        <span>{warning ?? (orderId ? `Gate ID: ${orderId}` : "الحماية الثابتة تبقى فعالة أثناء التأكيد.")}</span>
      </div>
    </div>
  );
}

function StrategiesOverview({
  strategies,
  metadata,
  busy,
  onSelect,
  onAction,
}: {
  strategies: StrategyOverviewItem[];
  metadata: StrategyTypeMetadata[];
  busy: string | null;
  onSelect: (id: string) => void;
  onAction: (strategy: StrategyInstance, action: "start" | "monitor" | "pause" | "stop") => void;
}) {
  const typeMap = new Map(metadata.map((item) => [item.type_id, item]));
  return (
    <section className="panel strategies-panel">
      <PanelHeader title="نظرة عامة على الاستراتيجيات" eyebrow="أداء وتشغيل من المحرك" icon="strategy" />
      {strategies.length === 0 ? (
        <EmptyState title="لا توجد استراتيجيات" description="القائمة تُنشأ من سجل الاستراتيجيات في المحرك." />
      ) : (
        <div className="table-scroll">
          <table className="strategies-overview-table">
            <thead>
              <tr>
                <th>الاستراتيجية</th>
                <th>الحالة</th>
                <th>الإشارة</th>
                <th>اليوم</th>
                <th>الإجمالي</th>
                <th>نسبة الفوز</th>
                <th>آخر نشاط</th>
                <th>التنبيه</th>
                <th>إجراءات</th>
              </tr>
            </thead>
            <tbody>
              {strategies.map((strategy) => {
                const lastActivity = strategy.last_trade_at ?? strategy.last_decision_at ?? strategy.updated_at;
                return (
                  <tr key={strategy.instance_id}>
                    <td>
                      <button className="table-link" type="button" onClick={() => onSelect(strategy.instance_id)}>
                        <strong>{strategy.name}</strong>
                        <small>
                          {typeMap.get(strategy.type_id)?.display_name_ar ?? strategy.type_id}
                          {` · ${strategy.symbol} · ${directionLabel(strategy.direction)}`}
                        </small>
                      </button>
                    </td>
                    <td><StatusPill label={strategyStatusLabel(strategy.status)} tone={strategyTone(strategy.status)} /></td>
                    <td><StatusPill label={signalLabel(strategy.current_signal)} tone={strategy.latest_decision_eligible ? "positive" : "neutral"} /></td>
                    <td dir="ltr">{formatMoney(strategy.today_realized_pnl)}</td>
                    <td dir="ltr">{formatMoney(strategy.total_realized_pnl)}</td>
                    <td dir="ltr">{formatPercent(strategy.win_rate_percentage)}</td>
                    <td>{formatDateTime(lastActivity)}</td>
                    <td>
                      {strategy.warning_codes.length > 0 ? (
                        <StatusPill label={strategyWarningLabel(strategy.warning_codes[0])} tone="warning" />
                      ) : (
                        <StatusPill label="لا يوجد" tone="positive" />
                      )}
                    </td>
                    <td>
                      <div className="row-actions">
                        <MiniAction label="فتح" disabled={busy !== null} onClick={() => onSelect(strategy.instance_id)} />
                        {strategy.status === "running" || strategy.status === "monitoring" ? (
                          <>
                            <MiniAction label="إيقاف مؤقت" disabled={busy !== null} onClick={() => onAction(strategy, "pause")} />
                            <MiniAction label="إيقاف" disabled={busy !== null} onClick={() => onAction(strategy, "stop")} />
                          </>
                        ) : (
                          <>
                            <MiniAction label="تشغيل" disabled={busy !== null} onClick={() => onAction(strategy, "start")} />
                            <MiniAction label="مراقبة" disabled={busy !== null} onClick={() => onAction(strategy, "monitor")} />
                          </>
                        )}
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

function RiskPanel({
  environment,
  modeState,
  bundle,
}: {
  environment: Environment | null;
  modeState: ModeState | null;
  bundle: ReturnType<typeof useDashboard>["bundle"];
}) {
  const risk = readyData(bundle.paperRisk);
  const gateRisk = environment === "live"
    ? readyData(bundle.liveRisk)
    : environment === "testnet"
      ? readyData(bundle.testnetRisk)
      : null;
  const snapshot = modeState?.snapshot;
  return (
    <section className="panel risk-panel">
      <PanelHeader title="إدارة المخاطر" eyebrow="حدود الحساب" icon="shield" />
      {environment === "paper" && risk ? (
        <div className="risk-progress-list">
          <ProgressRow
            label="الخسارة اليومية"
            value={Number(risk.realized_net_loss)}
            maximum={Number(risk.settings.daily_loss_limit)}
            display={`${formatMoney(risk.realized_net_loss)} / ${formatMoney(risk.settings.daily_loss_limit)}`}
          />
          <ProgressRow label="الصفقات الخاسرة" value={risk.losing_trades} maximum={risk.settings.losing_trade_limit} display={`${risk.losing_trades} / ${risk.settings.losing_trade_limit}`} />
          <ProgressRow label="الصفقات التلقائية" value={risk.automatic_fills} maximum={risk.settings.automatic_fill_limit} display={`${risk.automatic_fills} / ${risk.settings.automatic_fill_limit}`} />
          <InfoItem label="بداية اليوم" value={formatMoney(risk.baseline_balance)} />
          <InfoItem label="إدخالات يدوية" value={risk.manual_entries_blocked ? "محظورة" : "مسموحة"} />
          <InfoItem label="إدخالات تلقائية" value={risk.automatic_entries_blocked ? "محظورة" : "مسموحة"} />
        </div>
      ) : environment !== "paper" && snapshot && gateRisk ? (
        <div className="risk-progress-list">
          <ProgressRow
            label="خسارة حقوق الملكية اليومية"
            value={Number(gateRisk.equity_loss_used)}
            maximum={Number(gateRisk.policy.daily_loss_limit)}
            display={`${formatMoney(gateRisk.equity_loss_used)} / ${formatMoney(gateRisk.policy.daily_loss_limit)}`}
          />
          <ProgressRow
            label="الصفقات الخاسرة"
            value={gateRisk.losing_trades}
            maximum={gateRisk.policy.losing_trade_limit}
            display={`${gateRisk.losing_trades} / ${gateRisk.policy.losing_trade_limit}`}
          />
          <ProgressRow
            label="الصفقات التلقائية"
            value={gateRisk.automatic_trades}
            maximum={gateRisk.policy.automatic_trade_limit}
            display={`${gateRisk.automatic_trades} / ${gateRisk.policy.automatic_trade_limit}`}
          />
          <div className="info-grid compact-info-grid">
            <InfoItem label="خط الأساس اليومي" value={formatMoney(gateRisk.baseline_equity)} />
            <InfoItem label="حقوق الملكية الحالية" value={formatMoney(gateRisk.current_equity)} />
            <InfoItem label="الخسارة المتبقية" value={formatMoney(gateRisk.remaining_loss_allowance)} />
            <InfoItem label="إدخالات يدوية" value={gateRisk.manual_entries_blocked ? "محظورة" : "مسموحة"} />
            <InfoItem label="إدخالات تلقائية" value={gateRisk.automatic_entries_blocked ? "محظورة" : "مسموحة"} />
            <InfoItem
              label="سبب الحظر"
              value={gateRisk.blocked_reason_codes.length > 0
                ? gateRisk.blocked_reason_codes.map(strategyWarningLabel).join("، ")
                : "لا يوجد"}
            />
          </div>
          <div className="risk-check-grid">
            <RiskCheck label="المصالحة" healthy={!snapshot.reconciliation_error && !snapshot.unmanaged_state} />
            <RiskCheck label="One-way" healthy={snapshot.one_way_confirmed} />
            <RiskCheck label="Cross margin" healthy={snapshot.cross_margin_confirmed} />
            <RiskCheck label="خط الأساس اليومي" healthy={snapshot.daily_baseline_ready && gateRisk.baseline_ready} />
            <RiskCheck label="محرك المخاطر" healthy={snapshot.risk_ready && !gateRisk.manual_entries_blocked} />
            <RiskCheck label="حماية المركز" healthy={snapshot.protection_ready} />
            <RiskCheck label="REST snapshot" healthy={snapshot.rest_snapshot_confirmed} />
            <RiskCheck label="Private stream" healthy={snapshot.subscription_confirmed} />
          </div>
        </div>
      ) : (
        <EmptyState title="بيانات المخاطر غير متاحة" description="يُعرض هذا الوضع بدلاً من قيم قديمة أو افتراضية." />
      )}
      {modeState?.emergency_stop && <div className="inline-alert error-alert"><Icon name="power" /> إيقاف الطوارئ مفعّل</div>}
    </section>
  );
}

function WatchlistPanel({
  bundle,
  symbolFilter,
}: {
  bundle: ReturnType<typeof useDashboard>["bundle"];
  symbolFilter: string | null;
}) {
  return (
    <section className="panel watchlist-panel">
      <PanelHeader title="قائمة المراقبة والفرص" eyebrow="بيانات Gate.io" icon="chart" />
      <StateView value={bundle.watchlist} unavailableLabel="قائمة المراقبة غير متاحة">
        {(watchlist) => {
          const items = symbolFilter
            ? watchlist.items.filter((item) => item.symbol === symbolFilter)
            : watchlist.items;
          return items.length === 0 ? (
            <EmptyState title="لا توجد عقود مطابقة" description={symbolFilter ? "العقد المحدد غير موجود في قائمة المراقبة الحالية." : "أضف عقداً ليجلب المحرك سعره الحقيقي من Gate.io."} />
          ) : (
            <div className="table-scroll">
              <table>
                <thead>
                  <tr>
                    <th>العقد</th>
                    <th>Last Price</th>
                    <th>الاتجاه</th>
                    <th>الحالة</th>
                    <th>الأولوية</th>
                  </tr>
                </thead>
                <tbody>
                  {items.map((item) => (
                    <tr key={item.symbol}>
                      <td dir="ltr"><strong>{item.symbol}</strong></td>
                      <td dir="ltr">{formatDecimal(item.last_price)}</td>
                      <td>{watchlistDirectionLabel(item.direction)}</td>
                      <td><StatusPill label={item.is_active ? "نشط" : item.monitoring_only ? "مراقبة" : "متوقف"} tone={item.is_active ? "positive" : "neutral"} /></td>
                      <td>{item.priority}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          );
        }}
      </StateView>
    </section>
  );
}

function AlertsPanel({
  environment,
  modeState,
  strategies,
  runtime,
}: {
  environment: Environment | null;
  modeState: ModeState | null;
  strategies: StrategyInstance[];
  runtime: RemoteData<{ lifecycle: string }>;
}) {
  const alerts: Array<{ title: string; detail: string; tone: "negative" | "warning" }> = [];
  if (runtime.status === "error") {
    alerts.push({ title: "المحرك غير متصل", detail: runtime.message, tone: "negative" });
  }
  if (environment !== null && environment !== "paper" && !modeState?.snapshot) {
    alerts.push({ title: "لا توجد مصالحة حديثة", detail: "لن تُعرض بيانات حساب قديمة على أنها حالية.", tone: "warning" });
  }
  if (modeState?.emergency_stop) {
    alerts.push({ title: "إيقاف الطوارئ", detail: "كل الإدخالات الجديدة محظورة.", tone: "negative" });
  }
  modeState?.blocked_reasons_ar.forEach((reason) => alerts.push({ title: "منع دخول", detail: reason, tone: "warning" }));
  strategies.filter((item) => item.status === "error").forEach((strategy) => alerts.push({ title: `خطأ في ${strategy.name}`, detail: "راجع سجل الاستراتيجية قبل الاستئناف.", tone: "negative" }));
  if (modeState?.snapshot && !modeState.snapshot.protection_ready) {
    alerts.push({ title: "خطأ حماية المركز", detail: "New entries are blocked until protection is restored.", tone: "negative" });
  }

  return (
    <section className="panel alerts-panel">
      <PanelHeader title="تنبيهات مهمة" eyebrow="يتطلب الانتباه" icon="alert" />
      {alerts.length === 0 ? (
        <EmptyState title="لا توجد تنبيهات حالية" description="لم تُرجع مصادر المحرك حالة تحتاج إلى تدخل." />
      ) : (
        <div className="alerts-list">
          {alerts.map((alert, index) => (
            <article className={`alert-item alert-${alert.tone}`} key={`${alert.title}-${index}`}>
              <Icon name="alert" />
              <div><strong>{alert.title}</strong><span>{alert.detail}</span></div>
            </article>
          ))}
        </div>
      )}
    </section>
  );
}

function OrdersPanel({
  environment,
  modeState,
  bundle,
  symbolFilter,
  onChanged,
}: {
  environment: Environment | null;
  modeState: ModeState | null;
  bundle: ReturnType<typeof useDashboard>["bundle"];
  symbolFilter: string | null;
  onChanged: () => void;
}) {
  const [cancelBusy, setCancelBusy] = useState(false);
  const [cancelError, setCancelError] = useState<string | null>(null);
  const orders = (modeState?.snapshot?.open_orders ?? []).filter(
    (order) => !symbolFilter || order.contract === symbolFilter,
  );

  async function cancelPendingPaperOrder() {
    if (!window.confirm("إلغاء أمر Paper Limit المعلق؟ لن يتغير أي مركز مفتوح أو رصيد.")) {
      return;
    }
    setCancelBusy(true);
    setCancelError(null);
    try {
      await cancelPaperPendingEntry();
      onChanged();
    } catch (error) {
      setCancelError(error instanceof Error ? error.message : "تعذر إلغاء أمر Paper المعلق.");
    } finally {
      setCancelBusy(false);
    }
  }
  return (
    <section className="panel orders-panel">
      <PanelHeader title="الأوامر المفتوحة" eyebrow="لقطة المصالحة الحالية" icon="trade" />
      {environment === "paper" ? (
        <StateView value={bundle.paperPendingEntry} unavailableLabel="تعذر تحميل أمر Paper المعلق">
          {(pending) => pending ? (
            <div className="paper-pending-order">
              <div className="position-direction-row">
                <StatusPill label={pending.direction === "long" ? "شراء / Long" : "بيع / Short"} tone={pending.direction === "long" ? "positive" : "negative"} />
                <span>{pending.symbol ?? "عقد غير مسجل"} · Paper Limit محلي</span>
              </div>
              <div className="detail-list">
                <InfoItem label="السعر المحدد" value={formatDecimal(pending.limit_price)} />
                <InfoItem label="الكمية" value={formatDecimal(pending.quantity)} />
                <InfoItem label="الهامش المخصص" value={formatMoney(pending.allocated_margin)} />
                <InfoItem label="الرافعة" value={`${pending.leverage}×`} />
                <InfoItem label="معدل رسم الدخول" value={formatPercent(Number(pending.entry_fee_rate) * 100)} />
                <InfoItem label="احتياطي الأمان" value={formatMoney(pending.safety_reserve)} />
                <InfoItem label="وقت الإنشاء" value={formatDateTime(pending.created_at)} />
                <InfoItem label="انتهاء الصلاحية" value={formatDateTime(pending.expires_at)} />
              </div>
              {cancelError && <div className="inline-alert error-alert" role="alert"><Icon name="alert" /><span>{cancelError}</span></div>}
              <button className="danger-button" type="button" disabled={cancelBusy} onClick={() => void cancelPendingPaperOrder()}>
                <Icon name="x" />
                {cancelBusy ? "جارٍ الإلغاء…" : "إلغاء الأمر المعلق"}
              </button>
            </div>
          ) : (
            <EmptyState title="لا توجد أوامر Paper معلقة" description="سيظهر هنا أمر Paper Limit بعد أن يلتزم به المحرك." />
          )}
        </StateView>
      ) : !modeState?.snapshot ? (
        <EmptyState title="الأوامر غير متاحة" description="يجب إتمام المصالحة قبل عرض أوامر Gate.io المفتوحة." />
      ) : orders.length === 0 ? (
        <EmptyState title="لا توجد أوامر مفتوحة" description="لقطة Gate.io الحالية لا تحتوي أوامر Futures مفتوحة." />
      ) : (
        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                <th>العقد</th>
                <th>الجانب</th>
                <th>النوع</th>
                <th>السعر</th>
                <th>الكمية</th>
                <th>المنفذ</th>
                <th>الحالة</th>
                <th>Reduce-only</th>
                <th>المالك / المصدر</th>
                <th>الإنشاء</th>
              </tr>
            </thead>
            <tbody>
              {orders.map((order) => (
                <tr key={order.order_id}>
                  <td dir="ltr"><strong>{order.contract}</strong></td>
                  <td><StatusPill label={order.side === "long" ? "شراء" : "بيع"} tone={order.side === "long" ? "positive" : "negative"} /></td>
                  <td>{order.order_type === "market" ? "Market" : "Limit"}</td>
                  <td dir="ltr">{formatDecimal(order.price, order.order_type === "market" ? "Market" : "غير متاح")}</td>
                  <td dir="ltr">{formatDecimal(order.quantity)}</td>
                  <td dir="ltr">{formatDecimal(order.filled_quantity)}</td>
                  <td>{order.status}</td>
                  <td>{order.reduce_only ? "نعم" : "لا"}</td>
                  <td>{orderOwnerLabel(order)}</td>
                  <td>{formatDateTime(order.created_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

function paperPositionOwnerLabel(position: PaperPosition): string {
  if (position.strategy_name) {
    return position.strategy_name;
  }
  if (position.origin === "manual") {
    return "تداول يدوي";
  }
  if (position.origin === "monitoring_conversion") {
    return "تحويل من المراقبة";
  }
  if (position.origin === "automatic_strategy") {
    return "استراتيجية تلقائية";
  }
  if (position.origin === "legacy_automatic") {
    return "تلقائي قديم";
  }
  return position.managed_by_rangebot ? "RangeBot" : "غير منسوب";
}

function positionOwnerLabel(position: ExchangePositionSnapshot): string {
  if (position.strategy_name) {
    return position.strategy_name;
  }
  if (position.origin === "manual") {
    return "تداول يدوي";
  }
  if (position.origin === "monitoring_conversion") {
    return "تحويل من المراقبة";
  }
  if (position.origin === "automatic_strategy") {
    return "استراتيجية تلقائية";
  }
  if (position.origin === "legacy_automatic") {
    return "تلقائي قديم";
  }
  return position.managed_by_rangebot ? "RangeBot" : "خارجي / غير مُدار";
}

function trailingStateLabel(
  state: "desired" | "active" | "error" | null,
): string {
  if (state === "active") return "نشط ومؤكد";
  if (state === "desired") return "بانتظار تأكيد Gate.io";
  if (state === "error") return "خطأ — الحماية الثابتة ما زالت فعالة";
  return "غير مستخدم";
}

function orderOwnerLabel(order: ExchangeOpenOrderSnapshot): string {
  if (order.strategy_name) {
    return order.strategy_name;
  }
  if (order.origin === "manual") {
    return "تداول يدوي";
  }
  if (order.origin === "monitoring_conversion") {
    return "تحويل من المراقبة";
  }
  if (order.origin === "automatic_strategy") {
    return "استراتيجية تلقائية";
  }
  if (order.origin === "legacy_automatic") {
    return "تلقائي قديم";
  }
  return order.managed_by_rangebot ? "RangeBot" : "خارجي / غير مُدار";
}

function dashboardPeriodLabel(period: DashboardFilters["period"]): string {
  if (period === "7d") return "7 أيام";
  if (period === "30d") return "30 يوماً";
  if (period === "all") return "كل السجل";
  return "اليوم";
}

function PerformancePanel({
  environment,
  modeState,
  period,
}: {
  environment: Environment | null;
  modeState: ModeState | null;
  period: DashboardFilters["period"];
}) {
  const [history, setHistory] = useState<RemoteData<AccountPerformanceSeries>>({ status: "loading" });
  const snapshot = modeState?.snapshot;

  useEffect(() => {
    if (environment === null) {
      setHistory({ status: "loading" });
      return undefined;
    }
    const controller = new AbortController();
    setHistory({ status: "loading" });
    void loadAccountPerformance(environment, period, controller.signal)
      .then((data) => {
        if (!controller.signal.aborted) setHistory({ status: "ready", data });
      })
      .catch((error: unknown) => {
        if (controller.signal.aborted) return;
        setHistory({
          status: "error",
          message: error instanceof Error ? error.message : "تعذر تحميل سجل الأداء.",
        });
      });
    return () => controller.abort();
  }, [environment, period]);

  return (
    <section className="panel performance-panel">
      <PanelHeader title="الأداء وصافي النتائج" eyebrow={`سجل الحساب · ${dashboardPeriodLabel(period)}`} icon="chart" />
      {environment === null ? (
        <div className="performance-empty">
          <EmptyState
            title="بيئة التداول غير معروفة"
            description="سيُحمّل سجل الأداء بعد استعادة إعدادات البيئة من المحرك."
          />
        </div>
      ) : (
        <StateView value={history} unavailableLabel="تعذر تحميل سجل الأداء">
          {(series) => (
            <>
              <div className="performance-metrics-grid">
                <MetricValue label="تغير حقوق الملكية" value={formatMoney(series.equity_change)} emphasized />
                <MetricValue label="نسبة التغير" value={formatPercent(series.equity_change_percentage)} />
                <MetricValue label="أقصى تراجع" value={formatPercent(series.maximum_drawdown_percentage)} />
                <MetricValue label="P&L المحقق" value={formatMoney(series.realized_pnl_total)} />
                <MetricValue label="P&L غير المحقق" value={formatMoney(series.unrealized_pnl)} />
                <MetricValue label="الصافي بعد الرسوم والتمويل" value={formatMoney(series.net_pnl_total)} />
                <MetricValue label="الرسوم" value={formatMoney(series.fees_total)} />
                <MetricValue label="التمويل" value={formatMoney(series.funding_total)} />
              </div>
              {series.points.length >= 2 ? (
                <AccountEquityChart series={series} />
              ) : (
                <EmptyState
                  title="لا توجد نقاط كافية لرسم المنحنى"
                  description={
                    environment === "paper"
                      ? "ستُضاف نقاط عند تغيّر حساب Paper وعند تحديث القيمة السوقية للمركز."
                      : "ستُضاف نقطة جديدة بعد كل مصالحة Gate.io ناجحة."
                  }
                />
              )}
              <div className="performance-source-note">
                <Icon name="shield" />
                <span>
                  {environment === "paper"
                    ? "القيم محفوظة من دفتر Paper المحلي ويحسب المحرك الرسوم والربح والتراجع."
                    : "القيم محفوظة من لقطات مصالحة Gate.io الموثوقة ويحسب المحرك التغير والتراجع."}
                  {" "}آخر نقطة: {formatDateTime(series.points.at(-1)?.occurred_at ?? snapshot?.reconciled_at ?? null)}
                </span>
              </div>
            </>
          )}
        </StateView>
      )}
    </section>
  );
}

function AccountEquityChart({ series }: { series: AccountPerformanceSeries }) {
  const width = 900;
  const height = 240;
  const paddingX = 30;
  const paddingY = 24;
  const values = series.points.map((point) => Number(point.total_equity));
  const minimum = Math.min(...values);
  const maximum = Math.max(...values);
  const range = Math.max(maximum - minimum, Math.abs(maximum) * 0.002, 1);
  const path = series.points.map((point, index) => {
    const x = paddingX + (index / Math.max(series.points.length - 1, 1)) * (width - paddingX * 2);
    const y = paddingY + ((maximum - Number(point.total_equity)) / range) * (height - paddingY * 2);
    return `${index === 0 ? "M" : "L"}${x.toFixed(2)},${y.toFixed(2)}`;
  }).join(" ");
  const positive = Number(series.equity_change ?? "0") >= 0;
  return (
    <div className="account-equity-chart" role="img" aria-label={`منحنى حقوق الملكية خلال ${dashboardPeriodLabel(series.period)}`}>
      <svg viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="none">
        <line x1={paddingX} y1={paddingY} x2={paddingX} y2={height - paddingY} className="equity-grid-line" />
        <line x1={paddingX} y1={height - paddingY} x2={width - paddingX} y2={height - paddingY} className="equity-grid-line" />
        <path d={path} className={positive ? "equity-line positive" : "equity-line negative"} />
      </svg>
      <div className="equity-chart-scale">
        <span dir="ltr">{formatMoney(maximum.toString())}</span>
        <span dir="ltr">{formatMoney(minimum.toString())}</span>
      </div>
      <div className="equity-chart-times">
        <span>{formatDateTime(series.points[0]?.occurred_at ?? null)}</span>
        <span>{formatDateTime(series.points.at(-1)?.occurred_at ?? null)}</span>
      </div>
    </div>
  );
}

function MetricValue({ label, value, emphasized = false }: { label: string; value: string; emphasized?: boolean }) {
  return (
    <div className={emphasized ? "performance-metric emphasized" : "performance-metric"}>
      <span>{label}</span>
      <strong dir="ltr">{value}</strong>
    </div>
  );
}

function activityCutoff(period: DashboardFilters["period"]): number | null {
  if (period === "all") return null;
  const days = period === "30d" ? 30 : period === "7d" ? 7 : 1;
  return Date.now() - days * 24 * 60 * 60 * 1000;
}

function RecentActivity({
  activity,
  eventType,
  period,
  environment,
  strategyId,
  symbol,
}: {
  activity: RemoteData<ActivityEvent[]>;
  eventType: DashboardFilters["eventType"];
  period: DashboardFilters["period"];
  environment: Environment | null;
  strategyId: string | null;
  symbol: string | null;
}) {
  const cutoff = activityCutoff(period);
  return (
    <section className="panel activity-panel">
      <PanelHeader title="النشاط الأخير" eyebrow="سجل موحد ومنقح من المحرك" icon="activity" />
      <StateView value={activity} unavailableLabel="تعذر تحميل سجل النشاط">
        {(events) => {
          const filtered = events.filter((event) => {
            if (eventType !== "all" && event.category !== eventType) return false;
            if (cutoff !== null && new Date(event.occurred_at).getTime() < cutoff) return false;
            if (event.environment !== null && event.environment !== environment) return false;
            if (strategyId !== null && event.strategy_instance_id !== strategyId) return false;
            if (symbol !== null && event.symbol !== symbol) return false;
            return true;
          });
          if (filtered.length === 0) {
            return (
              <EmptyState
                title="لا يوجد نشاط مطابق"
                description="غيّر فلاتر البيئة أو الاستراتيجية أو الفترة لرؤية أحداث أخرى."
              />
            );
          }
          return (
            <div className="timeline">
              {filtered.slice(0, 40).map((event) => (
                <article className="timeline-item" key={event.event_id}>
                  <span className={`timeline-dot ${event.severity}`} />
                  <div>
                    <strong>{event.title_ar}</strong>
                    <span>
                      {event.detail_ar}
                      {event.strategy_name ? ` · ${event.strategy_name}` : ""}
                      {event.symbol ? ` · ${event.symbol}` : ""}
                    </span>
                  </div>
                  <div className="timeline-meta">
                    <StatusPill label={activityCategoryLabel(event.category)} tone="neutral" />
                    <time>{formatDateTime(event.occurred_at)}</time>
                  </div>
                </article>
              ))}
            </div>
          );
        }}
      </StateView>
    </section>
  );
}

function activityCategoryLabel(category: ActivityEvent["category"]): string {
  const labels: Record<ActivityEvent["category"], string> = {
    decision: "قرار",
    strategy: "استراتيجية",
    order: "طلب",
    paper: "Paper",
    risk: "مخاطر",
    system: "نظام",
    connection: "اتصال",
    research: "بحث",
  };
  return labels[category];
}

function PanelHeader({
  title,
  eyebrow,
  icon,
  trailing,
}: {
  title: string;
  eyebrow: string;
  icon: IconName;
  trailing?: ReactNode;
}) {
  return (
    <header className="panel-header">
      <div className="panel-title-group">
        <span className="panel-icon"><Icon name={icon} /></span>
        <div><span className="eyebrow">{eyebrow}</span><h2>{title}</h2></div>
      </div>
      {trailing}
    </header>
  );
}

function InfoItem({ label, value }: { label: string; value: string }) {
  return <div className="info-item"><span>{label}</span><strong dir="auto">{value}</strong></div>;
}

function ProgressRow({ label, value, maximum, display }: { label: string; value: number; maximum: number; display: string }) {
  const percentage = maximum > 0 ? Math.min(100, Math.max(0, (value / maximum) * 100)) : 0;
  return (
    <div className="progress-row">
      <div><span>{label}</span><strong dir="ltr">{display}</strong></div>
      <div className="progress-track"><span style={{ width: `${percentage}%` }} /></div>
    </div>
  );
}

function RiskCheck({ label, healthy }: { label: string; healthy: boolean }) {
  return (
    <div className={healthy ? "risk-check healthy" : "risk-check danger"}>
      <Icon name={healthy ? "shield" : "alert"} />
      <span>{label}</span>
      <strong>{healthy ? "سليم" : "غير جاهز"}</strong>
    </div>
  );
}

function MiniAction({ label, disabled, onClick }: { label: string; disabled: boolean; onClick: () => void }) {
  return <button className="mini-button" type="button" disabled={disabled} onClick={onClick}>{label}</button>;
}

function readyData<T>(value: RemoteData<T>): T | null {
  return value.status === "ready" ? value.data : null;
}

function strategyTone(status: StrategyInstance["status"]): "positive" | "negative" | "warning" | "neutral" | "info" {
  if (status === "running") return "positive";
  if (status === "monitoring") return "info";
  if (status === "error") return "negative";
  if (status === "paused") return "warning";
  return "neutral";
}

function signalLabel(signal: string | null | undefined): string {
  const labels: Record<string, string> = {
    long: "إشارة شراء",
    short: "إشارة بيع",
    none: "لا يوجد دخول",
    eligible_long: "مؤهل للشراء",
    eligible_short: "مؤهل للبيع",
    waiting: "انتظار",
  };
  return signal ? (labels[signal] ?? signal) : "لا يوجد قرار";
}

function strategyWarningLabel(code: string | undefined): string {
  if (!code) return "لا يوجد";
  const labels: Record<string, string> = {
    strategy_error: "خطأ في الاستراتيجية",
    awaiting_first_decision: "بانتظار أول قرار",
    spread_too_wide: "السبريد مرتفع",
    market_data_stale: "بيانات السوق قديمة",
    runtime_context_unavailable: "سياق السوق غير متاح",
    cooldown_active: "فترة التهدئة نشطة",
    signal_not_reset: "الإشارة لم تُعد ضبطها",
    daily_baseline_unavailable: "خط الأساس اليومي غير متاح",
    daily_loss_limit_reached: "تم بلوغ حد الخسارة اليومية",
    losing_trade_limit_reached: "تم بلوغ حد الصفقات الخاسرة",
    automatic_trade_limit_reached: "تم بلوغ حد الصفقات التلقائية",
  };
  return labels[code] ?? code.replaceAll("_", " ");
}

function environmentLabel(environment: Environment | null): string {
  return environment ? environmentLabels[environment] : "البيئة غير متاحة";
}

function watchlistDirectionLabel(direction: "long_only" | "short_only" | "both"): string {
  if (direction === "long_only") return "شراء فقط";
  if (direction === "short_only") return "بيع فقط";
  return "الاتجاهان";
}

function stringValue(value: JsonValue | undefined): string | null {
  return typeof value === "string" ? value : null;
}

function displayJsonValue(value: JsonValue | undefined, unit: string | null): string {
  if (value === undefined || value === null) return "غير متاح";
  if (typeof value === "boolean") return value ? "نعم" : "لا";
  if (typeof value === "number" || typeof value === "string") {
    const formatted = formatDecimal(value, String(value));
    return unit === "percent" ? `${formatted}٪` : formatted;
  }
  if (Array.isArray(value)) return value.map((item) => String(item)).join("، ") || "لا يوجد";
  return "بيانات مركبة";
}
