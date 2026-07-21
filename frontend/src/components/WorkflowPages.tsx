import { useEffect, useRef, useState } from "react";
import type { ReactNode } from "react";

import {
  createStrategyFromTemplate,
  listBacktests,
  listStrategyTypes,
  loadAccountPerformance,
  runDiscoveryScan,
} from "../api";
import {
  approveStrategySetup,
  archiveStrategySetup,
  archiveStrategyTemplate,
  cancelPortfolioBacktest,
  checkPortfolioBacktestReadiness,
  convertOpportunity,
  createBotDeployment,
  createStrategySetup,
  createStrategyTemplate,
  defaultStrategySetupDefaults,
  deleteStrategySetup,
  deleteStrategyTemplate,
  loadBotDeployments,
  loadOpportunities,
  listPortfolioBacktests,
  loadPortfolioBacktest,
  loadStrategySetups,
  loadStrategyTemplates,
  loadWorkflowSummary,
  rebaseStrategySetup,
  refreshStrategySetupPrice,
  resetStrategySetupDefaults,
  runSetupBacktest,
  runPortfolioBacktest,
  updatePortfolioBacktestNotes,
  transitionBotDeployment,
  updateOpportunityStatus,
  updateStrategySetup,
  updateStrategyTemplate,
} from "../workflowApi";
import {
  directionLabel,
  formatDateTime,
  formatDecimal,
  formatMoney,
  formatPercent,
} from "../lib/format";
import type {
  AccountPerformanceSeries,
  BacktestPortfolioRequest,
  BacktestReadiness,
  BotDeployment,
  Environment,
  JsonValue,
  RemoteData,
  StoredBacktestRun,
  StoredPortfolioBacktestRun,
  StrategyCoinSetup,
  StrategyOpportunity,
  StrategySetupDefaults,
  StrategyTemplate,
  StrategyTypeMetadata,
  WorkflowSummary,
} from "../types";
import { ContractSymbolPicker } from "./ContractSymbolPicker";
import { Icon } from "./Icon";
import { EmptyState, StateView, StatusPill } from "./StateView";
import {
  StrategyConfigurationFields,
  strategySchemaDefaults,
} from "./StrategyConfigurationFields";

interface WorkflowData {
  summary: WorkflowSummary;
  templates: StrategyTemplate[];
  setups: StrategyCoinSetup[];
  opportunities: StrategyOpportunity[];
  deployments: BotDeployment[];
  backtests: StoredBacktestRun[];
  strategyTypes: StrategyTypeMetadata[];
}

function useWorkflowData() {
  const [state, setState] = useState<RemoteData<WorkflowData>>({ status: "loading" });

  async function refresh(signal?: AbortSignal) {
    try {
      const [summary, templates, setups, opportunities, deployments, backtests, strategyTypes] = await Promise.all([
        loadWorkflowSummary(signal),
        loadStrategyTemplates(false, signal),
        loadStrategySetups(undefined, false, signal),
        loadOpportunities(signal),
        loadBotDeployments(signal),
        listBacktests(signal),
        listStrategyTypes(signal),
      ]);
      setState({ status: "ready", data: { summary, templates, setups, opportunities, deployments, backtests, strategyTypes } });
    } catch (error) {
      if (error instanceof DOMException && error.name === "AbortError") return;
      setState({ status: "error", message: error instanceof Error ? error.message : "تعذر تحميل سير العمل." });
    }
  }

  useEffect(() => {
    const controller = new AbortController();
    void refresh(controller.signal);
    return () => controller.abort();
  }, []);

  return { state, refresh: () => refresh() };
}

function PageHeader({
  eyebrow,
  title,
  description,
  action,
}: {
  eyebrow: string;
  title: string;
  description: string;
  action?: ReactNode;
}) {
  return (
    <header className="page-heading workflow-page-heading">
      <div>
        <span className="eyebrow">{eyebrow}</span>
        <h1>{title}</h1>
        <p>{description}</p>
      </div>
      {action && <div className="heading-actions">{action}</div>}
    </header>
  );
}

function Feedback({ message, error = false }: { message: string | null; error?: boolean }) {
  if (!message) return null;
  return (
    <div className={`inline-alert ${error ? "error-alert" : "success-alert"}`} role={error ? "alert" : "status"}>
      <Icon name={error ? "alert" : "shield"} />
      <span>{message}</span>
    </div>
  );
}

export function WorkflowHomePanel({
  onOpenStrategies,
  onOpenOpportunities,
  onOpenBacktesting,
}: {
  onOpenStrategies: () => void;
  onOpenOpportunities: () => void;
  onOpenBacktesting: () => void;
}) {
  const { state } = useWorkflowData();
  return (
    <section className="panel workflow-home-panel">
      <div className="panel-header">
        <div>
          <span className="eyebrow">سير العمل</span>
          <h2>من الاستراتيجية إلى البوت</h2>
          <p>كل تشغيل يمر عبر إعداد عملة، اختبار تاريخي، اعتماد، ونسخة نشر ثابتة.</p>
        </div>
      </div>
      <StateView value={state} unavailableLabel="تعذر تحميل ملخص سير العمل">
        {(data) => (
          <>
            <div className="workflow-summary-grid">
              <WorkflowMetric label="الاستراتيجيات" value={data.summary.templates} />
              <WorkflowMetric label="إعدادات العملات" value={data.summary.setups} />
              <WorkflowMetric label="فرص للمراجعة" value={data.summary.opportunities_new} tone="info" />
              <WorkflowMetric label="تحتاج اختباراً" value={data.summary.backtests_required} tone="warning" />
              <WorkflowMetric label="جاهزة للاعتماد" value={data.summary.approvals_ready} tone="positive" />
              <WorkflowMetric label="بوتات تعمل" value={data.summary.deployments_running} tone="positive" />
            </div>
            <div className="workflow-next-actions">
              <button className="primary-button" type="button" onClick={onOpenStrategies}>
                <Icon name="strategy" /> إدارة الاستراتيجيات
              </button>
              <button className="secondary-button" type="button" onClick={onOpenOpportunities}>
                <Icon name="activity" /> مراجعة الفرص
              </button>
              <button className="secondary-button" type="button" onClick={onOpenBacktesting}>
                <Icon name="chart" /> الاختبار التاريخي
              </button>
            </div>
          </>
        )}
      </StateView>
    </section>
  );
}

function WorkflowMetric({ label, value, tone = "neutral" }: { label: string; value: number; tone?: string }) {
  return (
    <div className={`workflow-metric workflow-metric-${tone}`}>
      <strong>{value}</strong>
      <span>{label}</span>
    </div>
  );
}

export function StrategiesPage({
  strategyTypes,
  onOpenSetup,
}: {
  strategyTypes: StrategyTypeMetadata[];
  onOpenSetup: (setupId: string) => void;
}) {
  const { state, refresh } = useWorkflowData();
  const [creating, setCreating] = useState(false);
  const [editingTemplateId, setEditingTemplateId] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [feedback, setFeedback] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const firstType = strategyTypes[0] ?? null;
  const [typeId, setTypeId] = useState(firstType?.type_id ?? "");
  const metadata = strategyTypes.find((item) => item.type_id === typeId) ?? firstType;
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [timeframe, setTimeframe] = useState(metadata?.supported_timeframes[0] ?? 5);
  const [direction, setDirection] = useState<"long" | "short" | "both">("both");
  const [configuration, setConfiguration] = useState<Record<string, JsonValue>>(
    metadata ? strategySchemaDefaults(metadata) : {},
  );
  const [defaults, setDefaults] = useState(defaultStrategySetupDefaults());
  const [coinDrafts, setCoinDrafts] = useState<Record<string, string>>({});

  useEffect(() => {
    if (!typeId && firstType) setTypeId(firstType.type_id);
  }, [firstType, typeId]);

  function chooseType(nextTypeId: string) {
    const next = strategyTypes.find((item) => item.type_id === nextTypeId);
    setTypeId(nextTypeId);
    if (next) {
      setTimeframe(next.supported_timeframes[0] ?? 5);
      setConfiguration(strategySchemaDefaults(next));
      setDirection(next.supports_long && next.supports_short ? "both" : next.supports_long ? "long" : "short");
    }
  }

  async function submitTemplate() {
    if (!metadata || !name.trim()) return;
    setBusy(true);
    setError(null);
    try {
      if (editingTemplateId) {
        await updateStrategyTemplate(editingTemplateId, {
          name: name.trim(),
          description: description.trim(),
          timeframe_minutes: timeframe,
          direction,
          configuration,
          setup_defaults: defaults,
          status: "active",
        });
      } else {
        await createStrategyTemplate({
          type_id: metadata.type_id,
          name: name.trim(),
          description: description.trim(),
          timeframe_minutes: timeframe,
          direction,
          configuration,
          setup_defaults: defaults,
          status: "active",
        });
      }
      setName("");
      setDescription("");
      setEditingTemplateId(null);
      setCreating(false);
      setFeedback(editingTemplateId
        ? "تم حفظ إصدار استراتيجية جديد. العملات الحالية بقيت مثبتة على إصداراتها السابقة."
        : "تم حفظ استراتيجية قابلة لإعادة الاستخدام دون ربطها بعملة واحدة.");
      await refresh();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "تعذر حفظ الاستراتيجية.");
    } finally {
      setBusy(false);
    }
  }

  async function addCoin(templateId: string) {
    const symbol = (coinDrafts[templateId] ?? "").trim().toUpperCase().replace("/", "_");
    if (!symbol) return;
    setBusy(true);
    setError(null);
    try {
      const setup = await createStrategySetup({ template_id: templateId, symbol });
      setCoinDrafts((current) => ({ ...current, [templateId]: "" }));
      setFeedback(`تمت إضافة ${symbol}. الإعداد ينتظر الاختبار التاريخي.`);
      await refresh();
      onOpenSetup(setup.setup_id);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "تعذر إضافة العملة.");
    } finally {
      setBusy(false);
    }
  }

  async function archiveTemplate(templateId: string) {
    setBusy(true);
    setError(null);
    try {
      await archiveStrategyTemplate(templateId);
      setFeedback("تمت أرشفة الاستراتيجية مع الاحتفاظ بتاريخها.");
      await refresh();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "تعذرت الأرشفة.");
    } finally {
      setBusy(false);
    }
  }

  async function removeTemplate(templateId: string) {
    setBusy(true);
    setError(null);
    try {
      await deleteStrategyTemplate(templateId);
      setFeedback("تم حذف مسودة الاستراتيجية غير المستخدمة.");
      await refresh();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "تعذر حذف المسودة.");
    } finally {
      setBusy(false);
    }
  }

  function editTemplate(template: StrategyTemplate) {
    setEditingTemplateId(template.template_id);
    setTypeId(template.type_id);
    setName(template.name);
    setDescription(template.description);
    setTimeframe(template.timeframe_minutes);
    setDirection(template.direction);
    setConfiguration(template.configuration);
    setDefaults(template.setup_defaults);
    setCreating(true);
    setFeedback(null);
    setError(null);
  }

  function startCreating() {
    const type = firstType;
    setEditingTemplateId(null);
    setName("");
    setDescription("");
    if (type) {
      chooseType(type.type_id);
      setDefaults(defaultStrategySetupDefaults());
    }
    setCreating(true);
  }

  return (
    <div className="dashboard-content workflow-page">
      <PageHeader
        eyebrow="قواعد قابلة لإعادة الاستخدام"
        title="الاستراتيجيات"
        description="أنشئ الاستراتيجية مرة واحدة، ثم أضف لها عدة إعدادات عملات مستقلة بالإرث والتجاوزات والإصدارات."
        action={(
          <button className="primary-button" type="button" onClick={() => creating ? setCreating(false) : startCreating()}>
            <Icon name="plus" /> {creating ? "إغلاق المنشئ" : "إنشاء استراتيجية"}
          </button>
        )}
      />
      <Feedback message={error ?? feedback} error={Boolean(error)} />

      {creating && metadata && (
        <section className="panel workflow-builder-panel">
          <div className="panel-header"><div><h2>{editingTemplateId ? "تعديل الاستراتيجية وإنشاء إصدار جديد" : "منشئ الاستراتيجية المرئي"}</h2><p>لا تحتاج إلى كتابة JSON. الحقول تأتي من سجل الاستراتيجيات في المحرك.</p></div></div>
          <div className="field-group two-columns">
            <label className="field"><span>نوع الاستراتيجية</span><select disabled={Boolean(editingTemplateId)} value={metadata.type_id} onChange={(event) => chooseType(event.target.value)}>{strategyTypes.map((item) => <option key={item.type_id} value={item.type_id}>{item.display_name_ar}</option>)}</select></label>
            <label className="field"><span>اسم الاستراتيجية</span><input value={name} onChange={(event) => setName(event.target.value)} placeholder="مثال: اتجاه متوسط المدى" /></label>
          </div>
          <label className="field"><span>الوصف</span><textarea value={description} onChange={(event) => setDescription(event.target.value)} placeholder="متى تستخدم هذه القواعد وما الهدف منها؟" /></label>
          <div className="field-group two-columns">
            <label className="field"><span>الإطار الافتراضي</span><select value={timeframe} onChange={(event) => setTimeframe(Number(event.target.value))}>{metadata.supported_timeframes.map((value) => <option key={value} value={value}>{timeframeText(value)}</option>)}</select></label>
            <label className="field"><span>الاتجاه الافتراضي</span><select value={direction} onChange={(event) => setDirection(event.target.value as typeof direction)}><option value="both">شراء وبيع</option>{metadata.supports_long && <option value="long">شراء فقط</option>}{metadata.supports_short && <option value="short">بيع فقط</option>}</select></label>
          </div>
          <StrategyConfigurationFields metadata={metadata} configuration={configuration} onChange={(key, value) => setConfiguration((current) => ({ ...current, [key]: value }))} />
          <SetupDefaultsEditor
            value={defaults}
            strategyTypeId={metadata.type_id}
            onChange={setDefaults}
          />
          <div className="form-actions"><button className="primary-button" type="button" disabled={busy || !name.trim()} onClick={() => void submitTemplate()}><Icon name="shield" />{busy ? "جارٍ الحفظ…" : editingTemplateId ? "حفظ إصدار جديد" : "حفظ الاستراتيجية"}</button></div>
        </section>
      )}

      <StateView value={state} unavailableLabel="تعذر تحميل الاستراتيجيات">
        {(data) => data.templates.length === 0 ? (
          <EmptyState title="لا توجد استراتيجيات بعد" description="ابدأ بإنشاء قواعد الاستراتيجية، ثم أضف العملات يدوياً أو من صفحة الفرص." />
        ) : (
          <div className="workflow-template-grid">
            {data.templates.map((template) => {
              const setups = data.setups.filter((setup) => setup.template_id === template.template_id);
              const type = strategyTypes.find((item) => item.type_id === template.type_id);
              return (
                <article className="panel workflow-template-card" key={template.template_id}>
                  <header>
                    <div><span className="eyebrow">{type?.display_name_ar ?? template.type_id}</span><h2>{template.name}</h2><p>{template.description || "لا يوجد وصف محفوظ."}</p></div>
                    <StatusPill label={template.status === "active" ? "نشطة" : "مسودة"} tone={template.status === "active" ? "positive" : "neutral"} />
                  </header>
                  <div className="workflow-fact-row"><span>{timeframeText(template.timeframe_minutes)}</span><span>{directionLabel(template.direction)}</span><span>الإصدار {template.current_revision}</span><span>{template.setup_count} عملة</span></div>
                  <div className="workflow-coin-list">
                    {setups.length === 0 ? <span className="muted-text">لم تُضف عملة بعد.</span> : setups.map((setup) => (
                      <button className="workflow-coin-row" type="button" key={setup.setup_id} onClick={() => onOpenSetup(setup.setup_id)}>
                        <span><strong dir="ltr">{setup.symbol}</strong><small>{setupStatusLabel(setup.status)}</small></span>
                        <span className={`price-state price-state-${setup.price_state}`}>{formatDecimal(setup.current_price)}</span>
                      </button>
                    ))}
                  </div>
                  <div className="workflow-add-coin-row">
                    <ContractSymbolPicker
                      value={coinDrafts[template.template_id] ?? ""}
                      onChange={(value) => setCoinDrafts((current) => ({ ...current, [template.template_id]: value }))}
                      environment="paper"
                      label="Add coin"
                      help="Choose a Gate contract or enter a symbol manually; the backend validates it before saving."
                    />
                    <button className="primary-button" type="button" disabled={busy} onClick={() => void addCoin(template.template_id)}><Icon name="plus" /> إضافة عملة</button>
                    <button className="secondary-button" type="button" disabled={busy} onClick={() => editTemplate(template)}><Icon name="settings" /> تعديل</button>
                    <button className="secondary-button" type="button" disabled={busy} onClick={() => void archiveTemplate(template.template_id)}><Icon name="archive" /> أرشفة</button>
                    <button className="danger-button" type="button" disabled={busy || template.status !== "draft" || template.setup_count > 0} onClick={() => void removeTemplate(template.template_id)}><Icon name="x" /> حذف المسودة</button>
                  </div>
                </article>
              );
            })}
          </div>
        )}
      </StateView>
    </div>
  );
}

function SetupDefaultsEditor({
  value,
  strategyTypeId,
  onChange,
}: {
  value: StrategySetupDefaults;
  strategyTypeId: string;
  onChange: (value: StrategySetupDefaults) => void;
}) {
  const supportsDca = strategyTypeId === "fixed_price_ladder";
  const supportsLimitTakeProfit = strategyTypeId === "fixed_price_ladder";
  function setRisk<K extends keyof StrategySetupDefaults["risk"]>(key: K, next: StrategySetupDefaults["risk"][K]) {
    onChange({ ...value, risk: { ...value.risk, [key]: next } });
  }
  function setDca<K extends keyof StrategySetupDefaults["dca"]>(key: K, next: StrategySetupDefaults["dca"][K]) {
    const dca = { ...value.dca, [key]: next };
    if (key === "enabled" && next === false) dca.maximum_entries = 1;
    onChange({ ...value, dca });
  }
  function setEntry(next: Partial<StrategySetupDefaults["execution_plan"]["entry"]>) {
    onChange({ ...value, execution_plan: { ...value.execution_plan, entry: { ...value.execution_plan.entry, ...next } } });
  }
  function setExit(key: "take_profit" | "stop_loss" | "strategy_exit" | "manual_exit", next: Partial<StrategySetupDefaults["execution_plan"]["take_profit"]>) {
    onChange({ ...value, execution_plan: { ...value.execution_plan, [key]: { ...value.execution_plan[key], ...next } } });
  }
  return (
    <div className="workflow-defaults-editor">
      <div className="section-title-row"><div><span className="eyebrow">إعدادات ترثها العملات</span><h3>التنفيذ وDCA والمخاطر</h3></div></div>
      <div className="field-group three-columns">
        <label className="field"><span>الهامش الافتراضي</span><input inputMode="decimal" value={value.risk.requested_margin} onChange={(event) => setRisk("requested_margin", event.target.value)} /></label>
        <label className="field"><span>الرافعة الافتراضية</span><input type="number" min={1} max={100} value={value.risk.requested_leverage} onChange={(event) => setRisk("requested_leverage", Number(event.target.value))} /></label>
        <label className="field"><span>أقصى تعرض %</span><input inputMode="decimal" value={value.risk.maximum_exposure_percentage} onChange={(event) => setRisk("maximum_exposure_percentage", event.target.value)} /></label>
      </div>
      <div className="workflow-execution-grid">
        <ExecutionEditor
          title="الدخول"
          orderType={value.execution_plan.entry.order_type}
          onOrderType={(order_type) => setEntry({
            order_type,
            limit_price: null,
            limit_price_formula: order_type === "market"
              ? null
              : value.execution_plan.entry.limit_price_formula ?? "last",
          })}
          limitLabel="صيغة السعر"
          limitHelp="مثال: last أو best_bid أو last-1%"
          limitValue={value.execution_plan.entry.limit_price_formula ?? value.execution_plan.entry.limit_price}
          onLimitValue={(limit_price_formula) => setEntry({
            limit_price: null,
            limit_price_formula,
          })}
        />
        {(["take_profit", "stop_loss", "strategy_exit", "manual_exit"] as const).map((key) => {
          const labels = { take_profit: "جني الربح", stop_loss: "وقف الخسارة", strategy_exit: "خروج الاستراتيجية", manual_exit: "الخروج اليدوي" };
          const settings = value.execution_plan[key];
          const allowLimit = key === "take_profit" && supportsLimitTakeProfit;
          return (
            <ExecutionEditor
              key={key}
              title={labels[key]}
              orderType={settings.order_type}
              allowLimit={allowLimit}
              onOrderType={(order_type) => setExit(key, {
                order_type,
                limit_offset_percentage: order_type === "market"
                  ? null
                  : settings.limit_offset_percentage ?? "0.1",
              })}
              limitLabel="إزاحة Limit %"
              limitValue={settings.limit_offset_percentage}
              onLimitValue={(limit_offset_percentage) => setExit(key, { limit_offset_percentage })}
              fallback={settings.fallback_to_market}
              onFallback={(fallback_to_market) => setExit(key, { fallback_to_market })}
            />
          );
        })}
      </div>
      <div className="field-group three-columns">
        <label className="field checkbox-field"><input type="checkbox" disabled={!supportsDca} checked={value.dca.enabled} onChange={(event) => setDca("enabled", event.target.checked)} /><span>تفعيل DCA</span></label>
        <label className="field"><span>أقصى عدد دخولات</span><input type="number" min={1} max={100} disabled={!supportsDca || !value.dca.enabled} value={value.dca.maximum_entries} onChange={(event) => setDca("maximum_entries", Number(event.target.value))} /></label>
        <label className="field"><span>المسافة %</span><input inputMode="decimal" disabled={!supportsDca || !value.dca.enabled} value={value.dca.spacing_percentage} onChange={(event) => setDca("spacing_percentage", event.target.value)} /></label>
      </div>
      {!supportsDca && <small className="muted-text">DCA متعدد الدخول للقراءة فقط هنا؛ التنفيذ الحقيقي مدعوم حالياً في استراتيجية سلم الأسعار الثابت.</small>}
    </div>
  );
}

function ExecutionEditor({
  title,
  orderType,
  onOrderType,
  limitValue,
  onLimitValue,
  limitLabel = "القيمة",
  limitHelp,
  allowLimit = true,
  fallback,
  onFallback,
}: {
  title: string;
  orderType: "market" | "limit";
  onOrderType: (value: "market" | "limit") => void;
  limitValue: string | null;
  onLimitValue: (value: string | null) => void;
  limitLabel?: string;
  limitHelp?: string;
  allowLimit?: boolean;
  fallback?: boolean;
  onFallback?: (value: boolean) => void;
}) {
  return (
    <div className="workflow-execution-card">
      <strong>{title}</strong>
      <label className="field"><span>نوع التنفيذ</span><select value={orderType} onChange={(event) => onOrderType(event.target.value as "market" | "limit")}><option value="market">Market</option><option value="limit" disabled={!allowLimit}>Limit</option></select></label>
      {!allowLimit && <small className="muted-text">Limit غير مدعوم بأمان في مسار الحماية الحالي لهذا الخروج.</small>}
      {orderType === "limit" && <label className="field"><span>{limitLabel}</span><input dir="ltr" value={limitValue ?? ""} onChange={(event) => onLimitValue(event.target.value)} />{limitHelp && <small>{limitHelp}</small>}</label>}
      {onFallback && <label className="field checkbox-field"><input type="checkbox" checked={fallback ?? true} onChange={(event) => onFallback(event.target.checked)} /><span>Fallback إلى Market</span></label>}
      {orderType === "limit" && fallback === false && <small className="warning-text">قد لا يُنفذ أمر Limit ويبقى المركز مفتوحاً.</small>}
    </div>
  );
}

export function SetupReviewPage({
  setupId,
  environment,
  strategyTypes,
  onBack,
  onOpenBacktesting,
  onOpenTrading,
}: {
  setupId: string;
  environment: Environment;
  strategyTypes: StrategyTypeMetadata[];
  onBack: () => void;
  onOpenBacktesting: () => void;
  onOpenTrading: () => void;
}) {
  const { state, refresh } = useWorkflowData();
  const setup = state.status === "ready" ? state.data.setups.find((item) => item.setup_id === setupId) ?? null : null;
  const template = setup && state.status === "ready" ? state.data.templates.find((item) => item.template_id === setup.template_id) ?? null : null;
  const metadata = template ? strategyTypes.find((item) => item.type_id === template.type_id) ?? null : null;
  const [configuration, setConfiguration] = useState<Record<string, JsonValue>>({});
  const [defaults, setDefaults] = useState<StrategySetupDefaults | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [feedback, setFeedback] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (setup) {
      setDefaults(setup.effective_setup_defaults);
      setConfiguration(setup.effective_configuration);
    }
  }, [setup?.setup_id, setup?.revision]);

  async function perform(key: string, task: () => Promise<unknown>, success: string) {
    setBusy(key); setError(null); setFeedback(null);
    try { await task(); setFeedback(success); await refresh(); }
    catch (caught) { setError(caught instanceof Error ? caught.message : "تعذر إكمال العملية."); }
    finally { setBusy(null); }
  }

  function approveCurrentEnvironment() {
    const hasCurrentBacktest = Boolean(
      setup?.latest_backtest_id && setup.latest_backtest_revision === setup.revision,
    );
    if (hasCurrentBacktest && setup) {
      return perform(
        "approve",
        () => approveStrategySetup(
          setup.setup_id,
          environment,
          `Approve ${environment.toUpperCase()} from the setup review page.`,
        ),
        `Approved the current revision for ${environment.toUpperCase()}.`,
      );
    }
    if (!setup || !window.confirm(
      `This strategy has not been backtested for the current revision.\n\n` +
      `Approve it for ${environment.toUpperCase()} without backtesting?`,
    )) {
      return;
    }
    return perform(
      "approve",
      () => approveStrategySetup(
        setup.setup_id,
        environment,
        `Approved ${environment.toUpperCase()} without a historical backtest after explicit confirmation.`,
        { skipBacktest: true, confirmation: "APPROVE WITHOUT BACKTEST" },
      ),
      `Approved the current revision for ${environment.toUpperCase()} without a historical backtest.`,
    );
  }

  if (state.status !== "ready") {
    return <div className="dashboard-content workflow-page"><StateView value={state} unavailableLabel="تعذر تحميل إعداد العملة">{() => null}</StateView></div>;
  }
  if (!setup || !template || !defaults) {
    return <div className="dashboard-content workflow-page"><EmptyState title="إعداد العملة غير موجود" description="قد يكون مؤرشفاً أو حُذف كمسودة غير مستخدمة." action={<button className="secondary-button" type="button" onClick={onBack}>العودة</button>} /></div>;
  }

  const templateOutdated = setup.template_revision !== template.current_revision;
  return (
    <div className="dashboard-content workflow-page">
      <PageHeader eyebrow={template.name} title={setup.symbol} description="راجع السعر والإرث والتجاوزات والتنفيذ والاختبار والاعتماد قبل إنشاء البوت." action={<button className="secondary-button" type="button" onClick={onBack}><Icon name="chevron" /> العودة</button>} />
      <Feedback message={error ?? feedback} error={Boolean(error)} />
      <section className="panel setup-price-hero">
        <div><span className="eyebrow">السعر الحالي · Gate.io USDT Perpetual</span><strong dir="ltr">{formatDecimal(setup.current_price)}</strong><small>{setup.price_observed_at ? `آخر تحديث ${formatDateTime(setup.price_observed_at)}` : "لم يصل سعر بعد"}</small></div>
        <div><StatusPill label={setup.price_state === "fresh" ? "حديث" : setup.price_state === "delayed" ? "متأخر" : "غير متاح"} tone={setup.price_state === "fresh" ? "positive" : "warning"} /><button className="secondary-button" type="button" disabled={busy !== null} onClick={() => void perform("price", () => refreshStrategySetupPrice(setup.setup_id), "تم تحديث السعر من المحرك.")}><Icon name="refresh" /> تحديث السعر</button></div>
      </section>
      {templateOutdated && <div className="inline-alert warning-alert"><Icon name="alert" /><span>هذه العملة مثبتة على إصدار الاستراتيجية {setup.template_revision} بينما الإصدار الحالي {template.current_revision}. إعادة الأساس تنشئ نسخة إعداد جديدة وتلغي الاعتماد القديم.</span></div>}
      {setup.warnings.map((warning) => <div className="inline-alert warning-alert" key={warning}><Icon name="alert" /><span>{warning}</span></div>)}
      <div className="workflow-review-grid">
        <section className="panel">
          <div className="panel-header"><div><h2>هوية السوق والإرث</h2><p>القيم الموروثة من نسخة الاستراتيجية لا تتغير بصمت.</p></div></div>
          <div className="detail-facts-grid">
            <ReviewFact label="المنصة" value={setup.exchange} />
            <ReviewFact label="السوق" value={setup.market_type} />
            <ReviewFact label="عملة التسعير" value={setup.quote_currency} />
            <ReviewFact label="الإطار" value={timeframeText(setup.timeframe_minutes)} />
            <ReviewFact label="الاتجاه" value={directionLabel(setup.direction)} />
            <ReviewFact label="نسخة الإعداد" value={`#${setup.revision}`} />
            <ReviewFact label="نسخة الاستراتيجية" value={`#${setup.template_revision}`} />
            <ReviewFact label="الحالة" value={setupStatusLabel(setup.status)} />
          </div>
          <details className="workflow-json-details"><summary>القيم الموروثة والتجاوزات</summary><div className="workflow-config-columns"><div><h4>موروث</h4><pre>{JSON.stringify(setup.inherited_configuration, null, 2)}</pre></div><div><h4>تجاوزات العملة</h4><pre>{JSON.stringify(setup.configuration_overrides, null, 2)}</pre></div></div></details>
        </section>
        <section className="panel">
          <div className="panel-header"><div><h2>بوابات الجاهزية</h2><p>لا يمكن بدء التداول قبل اجتيازها بالترتيب.</p></div></div>
          <div className="workflow-gates">
            <div className="inline-alert warning-alert" role="note">
              Backtesting is optional. Approving without a current backtest requires explicit confirmation.
            </div>
            <GateRow done label="إعداد العملة مكتمل" />
            <GateRow done={Boolean(setup.latest_backtest_id && setup.latest_backtest_revision === setup.revision)} label="اختبار النسخة الحالية" />
            <GateRow done={setup.latest_backtest_assessment === "promising"} label="نتيجة واعدة" />
            <GateRow done={Boolean(setup.active_approval_mode)} label="اعتماد Paper / Testnet / Live" />
            <GateRow done={Boolean(setup.runtime_instance_id)} label="نسخة نشر ثابتة" />
          </div>
          <div className="workflow-gate-actions">
            <button className="primary-button" type="button" onClick={onOpenBacktesting}><Icon name="chart" /> تشغيل الاختبار</button>
            <button className="secondary-button" type="button" disabled={busy !== null} onClick={() => void approveCurrentEnvironment()}><Icon name="shield" /> {setup.latest_backtest_assessment === "promising" ? "اعتماد" : "اعتماد بدون اختبار"} {environment.toUpperCase()}</button>
            <button className="secondary-button" type="button" disabled={setup.active_approval_mode !== environment || busy !== null} onClick={() => void perform("deploy", () => createBotDeployment(setup.setup_id, environment), "تم إنشاء نسخة نشر ثابتة. افتح صفحة التداول لبدء البوت.")}><Icon name="power" /> إنشاء البوت</button>
            {setup.runtime_instance_id && <button className="secondary-button" type="button" onClick={onOpenTrading}><Icon name="trade" /> فتح التداول</button>}
          </div>
        </section>
      </div>
      <section className="panel">
        <div className="panel-header"><div><h2>إعدادات العملة والتنفيذ</h2><p>أي حفظ ينشئ نسخة جديدة ويلغي الاختبار والاعتماد للنسخة السابقة.</p></div><button className="secondary-button" type="button" disabled={busy !== null} onClick={() => void perform("reset", () => resetStrategySetupDefaults(setup.setup_id), "تمت إعادة إعدادات العملة إلى قيم الاستراتيجية الافتراضية.")}><Icon name="refresh" /> إعادة الافتراضيات</button></div>
        {metadata && (
          <section className="configuration-section">
            <div className="section-title-row"><div><span className="eyebrow">تجاوزات خاصة بهذه العملة</span><h3>شروط الاستراتيجية</h3></div></div>
            <StrategyConfigurationFields
              metadata={metadata}
              configuration={configuration}
              onChange={(key, value) => setConfiguration((current) => ({ ...current, [key]: value }))}
            />
          </section>
        )}
        <SetupDefaultsEditor
          value={defaults}
          strategyTypeId={template.type_id}
          onChange={setDefaults}
        />
        <div className="form-actions">
          <button
            className="primary-button"
            type="button"
            disabled={busy !== null}
            onClick={() => void perform(
              "save",
              () => updateStrategySetup(setup.setup_id, {
                configuration_overrides: buildConfigurationOverrides(
                  setup.inherited_configuration,
                  configuration,
                ),
                setup_defaults_override: defaults,
              }),
              "تم حفظ نسخة إعداد جديدة. يلزم اختبار واعتماد جديدان.",
            )}
          ><Icon name="shield" /> حفظ إعدادات العملة</button>
          {templateOutdated && <button className="secondary-button" type="button" disabled={busy !== null || Boolean(setup.runtime_instance_id)} onClick={() => void perform("rebase", () => rebaseStrategySetup(setup.setup_id), "تم تثبيت العملة على أحدث نسخة استراتيجية. يلزم اختبار واعتماد جديدان.")}><Icon name="refresh" /> اعتماد الإصدار الجديد</button>}
          <button className="secondary-button" type="button" disabled={busy !== null || Boolean(setup.runtime_instance_id)} onClick={() => void perform("archive", () => archiveStrategySetup(setup.setup_id), "تمت أرشفة إعداد العملة وتاريخه.")}><Icon name="archive" /> أرشفة</button>
          <button className="danger-button" type="button" disabled={busy !== null || !["draft", "ready_for_backtest", "backtest_required"].includes(setup.status) || Boolean(setup.latest_backtest_id) || Boolean(setup.runtime_instance_id)} onClick={() => void perform("delete", () => deleteStrategySetup(setup.setup_id), "تم حذف المسودة غير المستخدمة.")}><Icon name="x" /> حذف المسودة</button>
        </div>
      </section>
    </div>
  );
}

function ReviewFact({ label, value }: { label: string; value: string }) { return <div className="detail-fact"><span>{label}</span><strong>{value}</strong></div>; }
function GateRow({ done, label }: { done: boolean; label: string }) { return <div className={done ? "workflow-gate done" : "workflow-gate pending"}><Icon name={done ? "shield" : "alert"} /><span>{label}</span><strong>{done ? "مكتمل" : "مطلوب"}</strong></div>; }

export function OpportunitiesPage({
  strategyTypes,
  onOpenSetup,
  onOpenStrategy,
}: {
  strategyTypes: StrategyTypeMetadata[];
  onOpenSetup: (setupId: string) => void;
  onOpenStrategy: (instanceId: string) => void;
}) {
  const { state, refresh } = useWorkflowData();
  const scannable = strategyTypes.filter((item) => item.supports_scanning);
  const [typeId, setTypeId] = useState(scannable[0]?.type_id ?? "");
  const metadata = scannable.find((item) => item.type_id === typeId) ?? null;
  const [timeframe, setTimeframe] = useState(metadata?.supported_timeframes[0] ?? 5);
  const [configuration, setConfiguration] = useState<Record<string, JsonValue>>(metadata ? strategySchemaDefaults(metadata) : {});
  const [minimumVolume, setMinimumVolume] = useState("1000000");
  const [minimumScore, setMinimumScore] = useState(45);
  const [busy, setBusy] = useState<string | null>(null);
  const [feedback, setFeedback] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [templateSelection, setTemplateSelection] = useState<Record<string, string>>({});
  const [instanceTemplateSelection, setInstanceTemplateSelection] = useState<Record<string, string>>({});
  const [reviewedId, setReviewedId] = useState<string | null>(null);
  const [showHistory, setShowHistory] = useState(false);

  function selectType(nextId: string) {
    const next = scannable.find((item) => item.type_id === nextId);
    setTypeId(nextId);
    if (next) { setTimeframe(next.supported_timeframes[0] ?? 5); setConfiguration(strategySchemaDefaults(next)); }
  }
  async function scan() {
    if (!metadata) return;
    setBusy("scan"); setError(null);
    try {
      const effective = { ...configuration };
      const schemaProperties = metadata.configuration_schema.properties;
      if (
        typeof schemaProperties === "object"
        && schemaProperties !== null
        && !Array.isArray(schemaProperties)
        && "timeframe_minutes" in schemaProperties
      ) {
        effective.timeframe_minutes = timeframe;
      }
      await runDiscoveryScan({ strategy_type_id: metadata.type_id, timeframe_minutes: timeframe, configuration: effective, minimum_quote_volume: minimumVolume, maximum_symbols: 30, maximum_candidates: 20, minimum_score: minimumScore });
      setFeedback("اكتمل الفحص وحُفظت الفرص الجديدة مع السعر ووقت الاكتشاف.");
      await refresh();
    } catch (caught) { setError(caught instanceof Error ? caught.message : "تعذر فحص السوق."); }
    finally { setBusy(null); }
  }
  async function mutate(id: string, task: () => Promise<unknown>, success: string) {
    setBusy(id); setError(null);
    try { await task(); setFeedback(success); await refresh(); }
    catch (caught) { setError(caught instanceof Error ? caught.message : "تعذر تحديث Opportunity."); }
    finally { setBusy(null); }
  }

  async function reviewOpportunity(opportunity: StrategyOpportunity) {
    setReviewedId(opportunity.opportunity_id);
    if (opportunity.status === "new") {
      await mutate(
        opportunity.opportunity_id,
        () => updateOpportunityStatus(opportunity.opportunity_id, "reviewed"),
        "Opportunity Review opened and its reviewed state was saved.",
      );
    }
  }

  async function createInstance(opportunity: StrategyOpportunity, selectedTypeId: string) {
    const selected = strategyTypes.find((item) => item.type_id === selectedTypeId);
    if (!selected) return;
    const compatibleTimeframe = selected.supported_timeframes.includes(opportunity.timeframe_minutes)
      ? opportunity.timeframe_minutes
      : selected.supported_timeframes[0];
    const suggestedName = `${selected.display_name_en} · ${opportunity.symbol}`;
    const name = window.prompt("Strategy Instance name", suggestedName)?.trim();
    if (!name || !compatibleTimeframe) return;
    await mutate(
      opportunity.opportunity_id,
      async () => {
        const instance = await createStrategyFromTemplate({
          template_id: `builtin:${selected.type_id}`,
          name,
          environment: "paper",
          symbol: opportunity.symbol,
          timeframe_minutes: compatibleTimeframe,
          direction: opportunity.signal === "long" ? "long" : opportunity.signal === "short" ? "short" : "both",
          requested_margin: "20",
          requested_leverage: 1,
          configuration_overrides: {},
        });
        onOpenStrategy(instance.instance_id);
      },
      "Paper Strategy Instance created. Trading did not start automatically.",
    );
  }

  return (
    <div className="dashboard-content workflow-page">
      <PageHeader
        eyebrow="Current market only"
        title="Opportunities"
        description="Scanner results are research leads. Review, shortlist, or ignore them; none of these actions starts trading."
        action={(
          <button className="primary-button" type="button" disabled={busy !== null || !metadata} onClick={() => void scan()}>
            <Icon name="activity" />{busy === "scan" ? "Scanning…" : "Scan market now"}
          </button>
        )}
      />
      <Feedback message={error ?? feedback} error={Boolean(error)} />
      <section className="panel opportunity-scanner-panel">
        <div className="field-group three-columns">
          <label className="field">
            <span>Scanner Strategy</span>
            <select value={typeId} onChange={(event) => selectType(event.target.value)}>
              {strategyTypes.map((item) => (
                <option key={item.type_id} value={item.type_id} disabled={!item.supports_scanning}>
                  {item.display_name_en}{item.supports_scanning ? "" : " — scanner unavailable"}
                </option>
              ))}
            </select>
            <small>Disabled Strategies can still be used after a coin is discovered.</small>
          </label>
          <label className="field"><span>Timeframe</span><select value={timeframe} onChange={(event) => setTimeframe(Number(event.target.value))}>{metadata?.supported_timeframes.map((value) => <option key={value} value={value}>{timeframeText(value)}</option>)}</select></label>
          <label className="field"><span>Minimum score</span><input type="number" min={0} max={100} value={minimumScore} onChange={(event) => setMinimumScore(Number(event.target.value))} /></label>
        </div>
        <label className="field"><span>Minimum 24h volume in USDT</span><input inputMode="decimal" value={minimumVolume} onChange={(event) => setMinimumVolume(event.target.value)} /></label>
        {metadata && <StrategyConfigurationFields metadata={metadata} configuration={configuration} onChange={(key, value) => setConfiguration((current) => ({ ...current, [key]: value }))} />}
      </section>
      <div className="opportunity-toolbar">
        <button className="secondary-button" type="button" onClick={() => setShowHistory((value) => !value)}>
          <Icon name="archive" />{showHistory ? "Hide ignored/history" : "Show ignored/history"}
        </button>
      </div>
      <StateView value={state} unavailableLabel="تعذر تحميل Opportunities">
        {(data) => data.opportunities.length === 0 ? <EmptyState title="No saved Opportunities" description="Run a market scan. RangeBot does not fabricate candidates or prices." /> : (
          <div className="opportunity-grid">
            {data.opportunities.filter((item) => showHistory || !["ignored", "rejected", "expired"].includes(item.status)).map((opportunity) => {
              const compatible = data.templates.filter((template) => template.type_id === opportunity.strategy_type_id && template.status !== "archived");
              const selectedTemplate = templateSelection[opportunity.opportunity_id] ?? compatible[0]?.template_id ?? "";
              const selectedInstanceType = instanceTemplateSelection[opportunity.opportunity_id] ?? opportunity.strategy_type_id;
              const reviewOpen = reviewedId === opportunity.opportunity_id;
              return (
                <article className="panel opportunity-card" key={opportunity.opportunity_id}>
                  <header><div><span className="eyebrow">{opportunity.exchange} · {opportunity.market_type}</span><h2 dir="ltr">{opportunity.symbol}</h2><p>{opportunity.explanation_ar}</p></div><div className="opportunity-score"><strong>{opportunity.scanner_score}</strong><span>of 100</span></div></header>
                  <div className="opportunity-price"><span>Observed price</span><strong dir="ltr">{formatDecimal(opportunity.current_price)} {opportunity.quote_currency}</strong><small>{opportunity.price_observed_at ? formatDateTime(opportunity.price_observed_at) : "Unavailable"}</small><StatusPill label={opportunity.price_state} tone={opportunity.price_state === "fresh" ? "positive" : "warning"} /></div>
                  <div className="reason-chips">{opportunity.qualifying_factors.map((factor) => <span key={factor}>{factor}</span>)}</div>
                  {opportunity.warnings.map((warning) => <small className="warning-text" key={warning}>{warning}</small>)}
                  <div className="workflow-fact-row"><span>{timeframeText(opportunity.timeframe_minutes)}</span><span>{opportunity.signal}</span><span>{opportunityStatusLabel(opportunity.status)}</span><span>Expires {formatDateTime(opportunity.expires_at)}</span></div>
                  <div className="opportunity-actions">
                    <button className="secondary-button" type="button" disabled={busy !== null || ["converted", "expired", "rejected"].includes(opportunity.status)} onClick={() => void reviewOpportunity(opportunity)}>Review details</button>
                    <button className="secondary-button" type="button" disabled={busy !== null || ["converted", "expired", "rejected", "ignored"].includes(opportunity.status)} onClick={() => void mutate(opportunity.opportunity_id, () => updateOpportunityStatus(opportunity.opportunity_id, "approved"), "Opportunity shortlisted only. No Strategy was started.")}>Shortlist</button>
                    <button className="secondary-button" type="button" disabled={busy !== null || ["converted", "expired"].includes(opportunity.status)} onClick={() => void mutate(opportunity.opportunity_id, () => updateOpportunityStatus(opportunity.opportunity_id, "rejected"), "Opportunity rejected; its audit history remains available.")}>Reject</button>
                    {opportunity.status === "ignored" ? (
                      <button className="secondary-button" type="button" disabled={busy !== null} onClick={() => void mutate(opportunity.opportunity_id, () => updateOpportunityStatus(opportunity.opportunity_id, "reviewed"), "Undo complete; Opportunity returned to the active review queue.")}>Undo Ignore</button>
                    ) : (
                      <button className="secondary-button" type="button" disabled={busy !== null || ["converted", "expired"].includes(opportunity.status)} onClick={() => void mutate(opportunity.opportunity_id, () => updateOpportunityStatus(opportunity.opportunity_id, "ignored"), "Opportunity hidden from the active queue. Use Show ignored/history to undo.")}>Ignore</button>
                    )}
                    <select value={selectedTemplate} onChange={(event) => setTemplateSelection((current) => ({ ...current, [opportunity.opportunity_id]: event.target.value }))}><option value="">Create matching Coin Setup</option>{compatible.map((template) => <option key={template.template_id} value={template.template_id}>{template.name}</option>)}</select>
                    <button className="primary-button" type="button" disabled={busy !== null || !selectedTemplate || ["converted", "expired", "rejected", "ignored"].includes(opportunity.status)} onClick={() => void mutate(opportunity.opportunity_id, async () => { const setup = await convertOpportunity(opportunity.opportunity_id, selectedTemplate); onOpenSetup(setup.setup_id); }, "Opportunity converted to a Coin Setup. Trading did not start.")}><Icon name="plus" /> Create Coin Setup</button>
                  </div>
                  {reviewOpen && (
                    <section className="opportunity-review-panel" aria-label="Opportunity Review">
                      <div className="panel-header">
                        <div><h3>Opportunity Review</h3><p>Source scanner: {strategyTypes.find((item) => item.type_id === opportunity.strategy_type_id)?.display_name_en ?? opportunity.strategy_type_id}. Choosing another Strategy below does not change the discovery source.</p></div>
                        <button className="icon-button" type="button" onClick={() => setReviewedId(null)} aria-label="Close review"><Icon name="x" /></button>
                      </div>
                      <div className="detail-facts-grid">
                        <ReviewFact label="Symbol" value={opportunity.symbol} />
                        <ReviewFact label="Observed price" value={`${formatDecimal(opportunity.current_price)} ${opportunity.quote_currency}`} />
                        <ReviewFact label="Price state" value={opportunity.price_state} />
                        <ReviewFact label="Discovered" value={formatDateTime(opportunity.discovered_at)} />
                        <ReviewFact label="Expires" value={formatDateTime(opportunity.expires_at)} />
                        <ReviewFact label="Signal" value={opportunity.signal} />
                      </div>
                      <div><strong>Why it qualified</strong><ul className="warning-list opportunity-factor-list">{opportunity.qualifying_factors.map((factor) => <li key={factor}>{factor}</li>)}</ul></div>
                      {opportunity.warnings.length > 0 && <div className="inline-alert warning-alert"><Icon name="alert" /><span>{opportunity.warnings.join(" · ")}</span></div>}
                      <div className="opportunity-instance-builder">
                        <label className="field">
                          <span>Create Strategy Instance for this coin</span>
                          <select value={selectedInstanceType} onChange={(event) => setInstanceTemplateSelection((current) => ({ ...current, [opportunity.opportunity_id]: event.target.value }))}>
                            {strategyTypes.map((item) => {
                              const timeframeCompatible = item.supported_timeframes.length > 0;
                              const directionCompatible = opportunity.signal === "none" || item.supported_directions.includes(opportunity.signal) || item.supported_directions.includes("both");
                              const compatibleInstance = timeframeCompatible && directionCompatible && (item.supports_automatic_trading || item.supports_monitoring);
                              return <option key={item.type_id} value={item.type_id} disabled={!compatibleInstance}>{item.display_name_en}{compatibleInstance ? "" : " — incompatible"}</option>;
                            })}
                          </select>
                        </label>
                        <button className="primary-button" type="button" disabled={busy !== null || !selectedInstanceType} onClick={() => void createInstance(opportunity, selectedInstanceType)}><Icon name="plus" /> Create Paper Strategy Instance</button>
                        <small>This creates a stopped Paper Instance. It does not start trading and does not claim the chosen Strategy discovered the coin.</small>
                      </div>
                    </section>
                  )}
                </article>
              );
            })}
          </div>
        )}
      </StateView>
    </div>
  );
}

export function BacktestingPage({ initialSetupId, onOpenSetup }: { initialSetupId: string | null; onOpenSetup: (setupId: string) => void }) {
  const { state, refresh } = useWorkflowData();
  const [setupId, setSetupId] = useState(initialSetupId ?? "");
  const [step, setStep] = useState(1);
  const [mode, setMode] = useState<"manual_symbols" | "historical_scanner">("manual_symbols");
  const [symbols, setSymbols] = useState("");
  const [startDate, setStartDate] = useState(() => new Date(Date.now() - 90 * 86400000).toISOString().slice(0, 10));
  const [endDate, setEndDate] = useState(() => new Date().toISOString().slice(0, 10));
  const [startingBalance, setStartingBalance] = useState("1000");
  const [margin, setMargin] = useState("100");
  const [maximumPositions, setMaximumPositions] = useState(1);
  const [makerFee, setMakerFee] = useState("0.0002");
  const [takerFee, setTakerFee] = useState("0.0005");
  const [slippage, setSlippage] = useState("5");
  const [spread, setSpread] = useState("2");
  const [fallbackTakeProfit, setFallbackTakeProfit] = useState("5");
  const [fallbackStopLoss, setFallbackStopLoss] = useState("3");
  const [ambiguity, setAmbiguity] = useState<"conservative" | "optimistic" | "lower_timeframe" | "mark_ambiguous">("conservative");
  const [warmup, setWarmup] = useState(200);
  const [additionalTimeframes, setAdditionalTimeframes] = useState("");
  const [scanFrequency, setScanFrequency] = useState(1);
  const [maximumCandidates, setMaximumCandidates] = useState(20);
  const [positionSizing, setPositionSizing] = useState<"fixed_quote" | "percentage_available" | "percentage_starting" | "risk_based">("fixed_quote");
  const [positionSizePercentage, setPositionSizePercentage] = useState("10");
  const [riskPercentage, setRiskPercentage] = useState("1");
  const [hypothesis, setHypothesis] = useState("");
  const [advancedOpen, setAdvancedOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [stage, setStage] = useState("");
  const [activeBacktestId, setActiveBacktestId] = useState<string | null>(null);
  const [historyError, setHistoryError] = useState<string | null>(null);
  const runController = useRef<AbortController | null>(null);
  const [result, setResult] = useState<StoredPortfolioBacktestRun | null>(null);
  const [portfolioHistory, setPortfolioHistory] = useState<StoredPortfolioBacktestRun[]>([]);
  const [readiness, setReadiness] = useState<BacktestReadiness | null>(null);
  const [error, setError] = useState<string | null>(null);
  const setup = state.status === "ready" ? state.data.setups.find((item) => item.setup_id === setupId) ?? null : null;
  useEffect(() => { if (!setupId && state.status === "ready" && state.data.setups[0]) setSetupId(state.data.setups[0].setup_id); }, [setupId, state]);
  useEffect(() => {
    if (setup) {
      setSymbols(setup.symbol);
      setMargin(setup.effective_setup_defaults.risk.requested_margin);
      setMaximumPositions(setup.effective_setup_defaults.risk.maximum_positions);
    }
  }, [setup?.setup_id, setup?.revision]);
  useEffect(() => {
    let active = true;
    void listPortfolioBacktests()
      .then((items) => {
        if (active) {
          setPortfolioHistory(items);
          setHistoryError(null);
        }
      })
      .catch((caught: unknown) => {
        if (active) setHistoryError(caught instanceof Error ? caught.message : "Backtest history could not be loaded.");
      });
    return () => {
      active = false;
      runController.current?.abort();
    };
  }, []);

  function applyBeginnerPreset() {
    setStartingBalance("1000");
    setMargin("100");
    setMaximumPositions(1);
    setMakerFee("0.0002");
    setTakerFee("0.0005");
    setSlippage("5");
    setSpread("2");
    setFallbackTakeProfit("5");
    setFallbackStopLoss("3");
    setAmbiguity("conservative");
    setWarmup(200);
    setPositionSizing("fixed_quote");
    setPositionSizePercentage("10");
    setRiskPercentage("1");
    setAdvancedOpen(false);
    setStage("Beginner preset applied — realistic and conservative.");
  }

  async function cancelActiveBacktest() {
    runController.current?.abort();
    if (!activeBacktestId) {
      setBusy(false);
      setStage("Canceled before the Backtest was queued.");
      return;
    }
    try {
      const canceled = await cancelPortfolioBacktest(activeBacktestId);
      setResult(canceled);
      setStage(canceled.stage_message_ar);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Backtest cancellation failed.");
    } finally {
      setBusy(false);
      setActiveBacktestId(null);
    }
  }

  async function run() {
    if (!setup || state.status !== "ready") return;
    const template = state.data.templates.find((item) => item.template_id === setup.template_id);
    const strategyType = state.data.strategyTypes.find((item) => item.type_id === template?.type_id);
    const selectedSymbols = symbols.split(/[\s,]+/).map((item) => item.trim().toUpperCase()).filter(Boolean);
    if (!template || !strategyType || selectedSymbols.length === 0) { setError("اختر استراتيجية ورمزاً واحداً على الأقل."); return; }
    runController.current?.abort();
    const controller = new AbortController();
    runController.current = controller;
    setBusy(true); setError(null); setStage("Preparing Backtest request…");
    setActiveBacktestId(null);
    try {
      const dca = setup.effective_setup_defaults.dca;
      const allocations = dca.enabled
        ? dca.allocation_method === "custom" ? dca.custom_allocations : equalPercentageAllocations(dca.maximum_entries)
        : ["100"];
      setStage("تشغيل المحفظة والإشارات زمنياً…");
      const portfolioRequest: BacktestPortfolioRequest = {
        mode, setup_id: setup.setup_id, setup_revision: setup.revision,
        strategy_type_id: template.type_id, strategy_version: strategyType.version,
        scanner_version: mode === "historical_scanner" ? strategyType.version : null,
        exchange: "gateio", market_type: "usdt_perpetual", quote_currency: "USDT",
        symbols: selectedSymbols, timeframe_minutes: setup.timeframe_minutes,
        additional_timeframes: additionalTimeframes.split(/[\s,]+/).map(Number).filter((value) => Number.isInteger(value) && value > 0), configuration: setup.effective_configuration,
        parameter_overrides: {},
        start: new Date(`${startDate}T00:00:00Z`).toISOString(),
        end: new Date(`${endDate}T23:59:59Z`).toISOString(),
        warmup_candles: warmup, scan_frequency_candles: scanFrequency,
        maximum_candidates: maximumCandidates, universe_quality: "current_survivor",
        data_provider: "gateio_rest", data_version: null, code_version: null,
        pre_test_hypothesis: hypothesis,
        execution: {
          entry_expiration_candles: setup.effective_setup_defaults.execution_plan.entry.expires_after_minutes === null
            ? null
            : Math.max(1, Math.ceil(setup.effective_setup_defaults.execution_plan.entry.expires_after_minutes / setup.timeframe_minutes)),
          time_exit_candles: null,
          take_profit_order_type: setup.effective_setup_defaults.execution_plan.take_profit.order_type,
          stop_loss_order_type: setup.effective_setup_defaults.execution_plan.stop_loss.order_type,
          take_profit_percentage: null, stop_loss_percentage: null,
          dca_enabled: dca.enabled, dca_spacing_percentage: dca.spacing_percentage,
          dca_allocations: allocations, recalculate_target_after_dca: true,
          cooldown_candles: 0,
        },
        settings: {
          initial_balance: startingBalance, margin_per_trade: margin,
          leverage: setup.effective_setup_defaults.risk.requested_leverage,
          maker_fee_rate: makerFee, taker_fee_rate: takerFee,
          slippage_basis_points: slippage, spread_basis_points: spread,
          ambiguity_policy: ambiguity, position_sizing_mode: positionSizing,
          position_size_percentage: positionSizePercentage, risk_percentage: riskPercentage,
          maximum_positions: maximumPositions,
          maximum_allocation_percentage: setup.effective_setup_defaults.risk.maximum_exposure_percentage,
          default_take_profit_percentage: fallbackTakeProfit,
          default_stop_loss_percentage: fallbackStopLoss,
          minimum_trades_for_assessment: 5,
        },
      };
      setStage("Checking Backtest readiness…");
      const readinessCheck = await checkPortfolioBacktestReadiness(portfolioRequest);
      setReadiness(readinessCheck);
      if (!readinessCheck.ready) {
        throw new Error(`Backtest is not ready: ${readinessCheck.missing_rules.join(" ")}`);
      }
      let stored = await runPortfolioBacktest(portfolioRequest, controller.signal);
      setActiveBacktestId(stored.backtest_id);
      const deadline = Date.now() + 10 * 60 * 1000;
      let consecutivePollFailures = 0;
      while (!["completed", "failed", "canceled"].includes(stored.status)) {
        if (Date.now() >= deadline) {
          throw new Error("Backtest polling timed out after 10 minutes. Cancel or retry with a smaller date range.");
        }
        setStage(`${stored.stage_message_ar || stored.status} · ${stored.progress_percentage}%`);
        await new Promise((resolve) => window.setTimeout(resolve, 1500));
        try {
          stored = await loadPortfolioBacktest(stored.backtest_id, controller.signal);
          consecutivePollFailures = 0;
        } catch (pollError) {
          if (controller.signal.aborted) throw pollError;
          consecutivePollFailures += 1;
          if (consecutivePollFailures >= 3) throw pollError;
          setStage(`Temporary status refresh failure (${consecutivePollFailures}/3). Retrying…`);
          await new Promise((resolve) => window.setTimeout(resolve, 1000 * consecutivePollFailures));
        }
      }
      setResult(stored);
      setPortfolioHistory((items) => [stored, ...items.filter((item) => item.backtest_id !== stored.backtest_id)]);
      if (stored.status === "failed") {
        throw new Error(`${stored.failure_code ?? "backtest_failed"} · ${stored.failure_stage ?? "unknown"}: ${stored.failure_reason ?? "Backtest failed."}`);
      }
      setStage(stored.status === "canceled" ? "Backtest canceled." : "Backtest completed.");
      await refresh();
    } catch (caught) {
      if (!controller.signal.aborted) setError(caught instanceof Error ? caught.message : "Backtest could not run.");
    } finally {
      if (runController.current === controller) runController.current = null;
      setBusy(false);
      setActiveBacktestId(null);
    }
  }
  return (
    <div className="dashboard-content workflow-page">
      <PageHeader
        eyebrow="Deterministic historical simulation"
        title="Backtesting"
        description="Backtests are optional research. They never submit Orders to Paper or Gate.io."
        action={(
          <div className="page-header-actions">
            <button className="secondary-button" type="button" disabled={busy} onClick={applyBeginnerPreset}><Icon name="shield" /> Beginner preset</button>
            {busy ? <button className="danger-button" type="button" onClick={() => void cancelActiveBacktest()}><Icon name="x" /> Cancel Backtest</button> : <button className="primary-button" type="button" disabled={!setup || step !== 5} onClick={() => void run()}><Icon name="chart" /> Run Backtest</button>}
          </div>
        )}
      />
      <Feedback message={error ?? historyError} error />
      {!error && !historyError && stage && <div className="inline-alert neutral-alert" role="status"><Icon name="activity" /><span>{stage}</span></div>}
      <StateView value={state} unavailableLabel="تعذر تحميل إعدادات الاختبار">
        {(data) => data.setups.length === 0 ? <EmptyState title="لا توجد إعدادات عملات" description="أضف عملة إلى استراتيجية أولاً." /> : (
          <>
            <div className="backtest-stepper" aria-label="خطوات إعداد الاختبار">{["الاستراتيجية", "مصدر الفرص", "البيانات", "رأس المال والتنفيذ", "المراجعة"].map((label, index) => <button key={label} className={step === index + 1 ? "active" : ""} type="button" onClick={() => setStep(index + 1)}><span>{index + 1}</span>{label}</button>)}</div>
            <section className="panel backtest-control-panel">
              {step === 1 && <><div className="field-group two-columns"><label className="field"><span>إعداد العملة والاستراتيجية</span><select value={setupId} onChange={(event) => { setSetupId(event.target.value); setResult(null); setReadiness(null); }}><option value="">اختر إعداداً</option>{data.setups.map((item) => <option key={item.setup_id} value={item.setup_id}>{item.symbol} · {data.templates.find((template) => template.template_id === item.template_id)?.name}</option>)}</select></label><div className="review-callout"><strong>{readiness ? readiness.ready ? "جاهز للاختبار" : "غير جاهز للاختبار" : setup ? "سيُفحص قبل التشغيل" : "غير جاهز للاختبار"}</strong><p>{setup ? `نسخة الإعداد #${setup.revision} وإصدار الاستراتيجية سيبقيان ثابتين داخل النتيجة.` : "اختر إعداداً مكتمل القواعد."}</p>{readiness?.missing_rules.map((item) => <small key={item}>{item}</small>)}</div></div></>}
              {step === 2 && <div className="field-group"><div className="mode-choice"><button className={mode === "manual_symbols" ? "active" : ""} type="button" onClick={() => setMode("manual_symbols")}><strong>رموز يدوية</strong><small>تتجاوز الاكتشاف فقط، ولا تتجاوز محفز الدخول.</small></button><button className={mode === "historical_scanner" ? "active" : ""} type="button" onClick={() => setMode("historical_scanner")}><strong>إعادة تشغيل الماسح</strong><small>تقييم وترتيب تاريخي عند كل توقيت.</small></button></div><label className="field"><span>{mode === "historical_scanner" ? "كون الرموز التاريخي التقريبي" : "الرموز"}، مفصولة بفاصلة</span><textarea dir="ltr" value={symbols} onChange={(event) => setSymbols(event.target.value)} /></label>{mode === "historical_scanner" && <><div className="field-group two-columns"><label className="field"><span>تكرار المسح (شموع)</span><input type="number" min={1} value={scanFrequency} onChange={(event) => setScanFrequency(Number(event.target.value))} /></label><label className="field"><span>أقصى مرشحين في كل مسح</span><input type="number" min={1} value={maximumCandidates} onChange={(event) => setMaximumCandidates(Number(event.target.value))} /></label></div><div className="inline-alert warning-alert"><Icon name="alert" /><span>يستخدم هذا الإصدار كون العملات الحالية كبديل تاريخي، لذلك ستظهر ملاحظة تحيز العملات الباقية.</span></div></>}</div>}
              {step === 3 && <div className="field-group two-columns"><label className="field"><span>من تاريخ</span><input type="date" value={startDate} onChange={(event) => setStartDate(event.target.value)} /></label><label className="field"><span>إلى تاريخ</span><input type="date" value={endDate} onChange={(event) => setEndDate(event.target.value)} /></label><label className="field"><span>شموع التهيئة قبل البداية</span><input type="number" min={0} value={warmup} onChange={(event) => setWarmup(Number(event.target.value))} /></label><label className="field"><span>أطر إضافية بالدقائق</span><input dir="ltr" placeholder="15, 240" value={additionalTimeframes} onChange={(event) => setAdditionalTimeframes(event.target.value)} /></label><div className="review-callout"><strong>Gate.io · USDT Perpetual · {setup ? timeframeText(setup.timeframe_minutes) : "—"}</strong><p>تُستخدم الشموع المغلقة فقط، ولا تدخل فترة التهيئة في العائد المعلن.</p></div></div>}
              {step === 4 && (
                <div className="backtest-capital-step">
                  <div className="beginner-preset-card">
                    <div><strong>Beginner — realistic and conservative</strong><p>Uses conservative ambiguity, realistic fees, 5 bps Slippage, 2 bps Spread, one Position, and 200 warm-up candles.</p></div>
                    <button className="secondary-button" type="button" onClick={applyBeginnerPreset}>Apply preset</button>
                  </div>
                  <div className="field-group two-columns">
                    <label className="field"><span>Starting balance USDT</span><input dir="ltr" value={startingBalance} onChange={(event) => setStartingBalance(event.target.value)} /></label>
                    <label className="field"><span>Position sizing</span><select value={positionSizing} onChange={(event) => setPositionSizing(event.target.value as typeof positionSizing)}><option value="fixed_quote">Fixed quote amount</option><option value="percentage_available">Percentage available</option><option value="percentage_starting">Percentage starting balance</option><option value="risk_based">Risk-based</option></select></label>
                    {positionSizing === "fixed_quote" ? <label className="field"><span>Margin per Trade</span><input dir="ltr" value={margin} onChange={(event) => setMargin(event.target.value)} /></label> : positionSizing === "risk_based" ? <label className="field"><span>Risk per Trade %</span><input dir="ltr" value={riskPercentage} onChange={(event) => setRiskPercentage(event.target.value)} /></label> : <label className="field"><span>Position size %</span><input dir="ltr" value={positionSizePercentage} onChange={(event) => setPositionSizePercentage(event.target.value)} /></label>}
                    <label className="field"><span>Maximum simultaneous Positions</span><input type="number" min={1} value={maximumPositions} onChange={(event) => setMaximumPositions(Number(event.target.value))} /></label>
                  </div>
                  <button className="secondary-button advanced-settings-toggle" type="button" aria-expanded={advancedOpen} onClick={() => setAdvancedOpen((value) => !value)}><Icon name="settings" />{advancedOpen ? "Hide advanced execution assumptions" : "Show advanced execution assumptions"}</button>
                  {advancedOpen && (
                    <div className="field-group two-columns advanced-backtest-settings">
                      <label className="field"><span>Maker Fee</span><input dir="ltr" value={makerFee} onChange={(event) => setMakerFee(event.target.value)} /></label>
                      <label className="field"><span>Taker Fee</span><input dir="ltr" value={takerFee} onChange={(event) => setTakerFee(event.target.value)} /></label>
                      <label className="field"><span>Slippage (basis points)</span><input dir="ltr" value={slippage} onChange={(event) => setSlippage(event.target.value)} /></label>
                      <label className="field"><span>Spread (basis points)</span><input dir="ltr" value={spread} onChange={(event) => setSpread(event.target.value)} /></label>
                      <label className="field"><span>Fallback Take Profit %</span><input dir="ltr" value={fallbackTakeProfit} onChange={(event) => setFallbackTakeProfit(event.target.value)} /></label>
                      <label className="field"><span>Fallback Stop Loss %</span><input dir="ltr" value={fallbackStopLoss} onChange={(event) => setFallbackStopLoss(event.target.value)} /></label>
                      <label className="field"><span>Intrabar ambiguity</span><select value={ambiguity} onChange={(event) => setAmbiguity(event.target.value as typeof ambiguity)}><option value="conservative">Conservative: Stop Loss first</option><option value="optimistic">Optimistic: Take Profit first</option><option value="lower_timeframe">Use lower Timeframe</option><option value="mark_ambiguous">Mark Trade ambiguous</option></select></label>
                    </div>
                  )}
                </div>
              )}
              {step === 5 && <div className="backtest-review"><span className="eyebrow">Final step</span><h3>Review and run</h3><p>Signals are evaluated after each closed {setup ? timeframeText(setup.timeframe_minutes) : "—"} candle. Market Orders use {slippage} bps Slippage and {spread} bps Spread. Maker Fee {makerFee}; Taker Fee {takerFee}; fallback Take Profit / Stop Loss {fallbackTakeProfit}% / {fallbackStopLoss}%; maximum {maximumPositions} Positions; ambiguity policy {ambiguity}.</p><label className="field"><span>Optional: pre-test hypothesis</span><textarea value={hypothesis} onChange={(event) => setHypothesis(event.target.value)} /></label>{setup && <div className="workflow-fact-row"><span dir="ltr">{symbols}</span><span>Setup revision #{setup.revision}</span><button className="secondary-button" type="button" onClick={() => onOpenSetup(setup.setup_id)}>Optional: Open Setup Review</button></div>}<div className="final-step-action"><strong>No more setup steps.</strong><span>Run the Backtest now or go back to change an assumption.</span><button className="primary-button" type="button" disabled={busy || !setup} onClick={() => void run()}><Icon name="chart" /> Run Backtest</button></div></div>}
              <div className="wizard-actions"><button className="secondary-button" type="button" disabled={step === 1 || busy} onClick={() => setStep((value) => Math.max(1, value - 1))}>Previous</button>{step < 5 ? <button className="primary-button" type="button" disabled={busy} onClick={() => setStep((value) => Math.min(5, value + 1))}>Next</button> : <span className="wizard-final-label">Step 5 of 5 · Final step</span>}</div>
            </section>
            {result && <PortfolioBacktestResultPanel stored={result} onChange={setResult} />}
            <section className="panel"><div className="panel-header"><div><h2>آخر اختبارات المحفظة المحفوظة</h2><p>لقطات إعداد ونتائج ثابتة للبحث فقط؛ لا تدخل في P&amp;L الحساب. تُحمّل التفاصيل عند فتح نتيجة فقط.</p></div></div><div className="history-list">{portfolioHistory.length === 0 ? <EmptyState title="لا توجد اختبارات محفظة بعد" description="شغّل أول اختبار من الخطوات أعلاه." /> : portfolioHistory.slice(0, 20).map((item) => <div className="history-row" key={item.backtest_id}><div><strong dir="ltr">{item.request.symbols.join(", ")}</strong><small>{formatDateTime(item.created_at)} · {item.request.mode === "historical_scanner" ? "ماسح تاريخي" : "رموز يدوية"} · {item.status}</small></div><div>{item.result ? <><strong>{assessmentLabel(item.result.assessment.label)}</strong><small>{formatPercent(item.result.metrics.return_percentage)}</small><button className="secondary-button" type="button" onClick={() => setResult(item)}>فتح</button></> : <><strong>{item.stage_message_ar}</strong>{item.status === "completed" && <button className="secondary-button" type="button" onClick={() => void loadPortfolioBacktest(item.backtest_id).then(setResult)}>فتح</button>}</>}</div></div>)}</div></section>
          </>
        )}
      </StateView>
    </div>
  );
}

function PortfolioBacktestResultPanel({ stored, onChange }: { stored: StoredPortfolioBacktestRun; onChange: (value: StoredPortfolioBacktestRun) => void }) {
  const [tab, setTab] = useState<"overview" | "equity" | "trades" | "scanner" | "decisions" | "assumptions" | "notes">("overview");
  const [notes, setNotes] = useState(stored.post_test_observations);
  const [decisionSymbol, setDecisionSymbol] = useState("");
  const [decisionEvent, setDecisionEvent] = useState("");
  const result = stored.result;
  if (!result) return <section className="panel"><StatusPill label={stored.stage_message_ar || stored.status} tone={stored.status === "failed" ? "negative" : "warning"} /><p>{stored.failure_reason}</p></section>;
  const metrics = result.metrics;
  const filteredDecisions = (result.decisions ?? []).filter((decision) =>
    (!decisionSymbol || decision.symbol === decisionSymbol)
    && (!decisionEvent || decision.event === decisionEvent)
  );
  const promising = result.assessment.label === "promising";
  const tabs: Array<typeof tab> = ["overview", "equity", "trades", ...(stored.request.mode === "historical_scanner" ? ["scanner" as const] : []), "decisions", "assumptions", "notes"];
  return <section className={`panel backtest-result-panel assessment-${result.assessment.label}`}><div className="panel-header"><div><span className="eyebrow">تشغيل ثابت · {stored.configuration_hash.slice(0, 12)}</span><h2>{assessmentLabel(result.assessment.label)}</h2><p>{result.assessment.summary_ar}</p></div><StatusPill label={promising ? "مؤهل للمراجعة والاعتماد" : "يحتاج مراجعة"} tone={promising ? "positive" : "warning"} /></div><div className="backtest-result-tabs">{tabs.map((item) => <button className={tab === item ? "active" : ""} type="button" key={item} onClick={() => setTab(item)}>{({ overview: "نظرة عامة", equity: "الحقوق", trades: "الصفقات", scanner: "الماسح", decisions: "القرارات", assumptions: "الافتراضات", notes: "الملاحظات" } as const)[item]}</button>)}</div>
    {tab === "overview" && <><div className="backtest-metric-grid"><Result label="صافي العائد" value={formatPercent(metrics.return_percentage)} /><Result label="العائد الإجمالي" value={formatPercent(metrics.gross_return_percentage ?? "0")} /><Result label="الرصيد النهائي" value={formatMoney(metrics.ending_equity ?? metrics.ending_balance)} /><Result label="أقصى تراجع" value={formatPercent(metrics.maximum_drawdown_percentage)} /><Result label="نسبة الفوز" value={formatPercent(metrics.win_rate_percentage)} /><Result label="عامل الربح" value={formatDecimal(metrics.profit_factor)} /><Result label="التوقع/صفقة" value={formatMoney(metrics.expectancy ?? "0")} /><Result label="متوسط R" value={formatDecimal(metrics.average_r ?? null)} /><Result label="الرسوم" value={formatMoney(metrics.total_fees ?? metrics.fees)} /><Result label="الانزلاق" value={formatMoney(metrics.total_slippage ?? "0")} /><Result label="التعرض" value={formatPercent(metrics.exposure_percentage ?? "0")} /><Result label="صفقات غامضة" value={String(metrics.ambiguous_trades ?? 0)} /></div>{[...result.warnings, ...result.assessment.warnings].map((warning) => <div className="inline-alert warning-alert" key={warning}><Icon name="alert" /><span>{warning}</span></div>)}</>}
    {tab === "equity" && <div className="history-list">{result.equity_curve.map((point) => <div className="history-row" key={point.occurred_at}><span>{formatDateTime(point.occurred_at)}</span><div><strong>{formatMoney(point.equity)}</strong><small>نقد {formatMoney(point.cash ?? "0")} · مستثمر {formatMoney(point.invested_capital ?? "0")} · تراجع {formatPercent(point.drawdown_percentage)}</small></div></div>)}</div>}
    {tab === "trades" && <div className="history-list">{result.trades.length === 0 ? <EmptyState title="لا توجد صفقات" description="الاختبار صحيح، لكن شروط الدخول لم تنتج صفقة ضمن الفترة." /> : result.trades.map((trade) => <div className="history-row" key={trade.trade_number}><div><strong dir="ltr">{trade.symbol || result.spec.symbol}</strong><small>إشارة {formatDateTime(trade.signal_at)} · دخول {formatDateTime(trade.entered_at)} · خروج {formatDateTime(trade.exited_at)}</small><small>متوسط {formatDecimal(trade.average_entry_price ?? trade.entry_price)} · وقف {formatDecimal(trade.stop_loss_price ?? null)} · هدف {formatDecimal(trade.take_profit_price ?? null)} · {trade.exit_reason}{trade.ambiguous ? " · غامضة" : ""}</small><small>{(trade.entry_fills ?? []).map((fill) => `${fill.role} ${fill.quantity}@${fill.price}`).join(" · ")}</small><small>{trade.entry_explanation_ar}</small></div><div><strong>{formatMoney(trade.net_pnl)}</strong><small>إجمالي {formatMoney(trade.gross_pnl)} · رسوم {formatMoney(trade.fees)} · انزلاق {formatMoney(trade.slippage ?? "0")} · R {formatDecimal(trade.result_r ?? null)}</small></div></div>)}</div>}
    {tab === "scanner" && <><div className="backtest-metric-grid"><Result label="تم تقييمها" value={String((result.candidates ?? []).length)} /><Result label="مؤهلة" value={String((result.candidates ?? []).filter((item) => item.qualified).length)} /><Result label="مختارة" value={String((result.candidates ?? []).filter((item) => item.selected).length)} /><Result label="مرفوضة بعد التأهل" value={String((result.candidates ?? []).filter((item) => item.qualified && !item.selected).length)} /></div><div className="history-list">{(result.candidates ?? []).map((candidate, index) => <div className="history-row" key={`${candidate.occurred_at}-${candidate.symbol}-${index}`}><div><strong dir="ltr">#{candidate.rank} {candidate.symbol}</strong><small>{formatDateTime(candidate.occurred_at)} · {candidate.explanation_ar}</small><small dir="ltr">{JSON.stringify(candidate.factor_values)}</small></div><div><strong>{candidate.score}</strong><small>{candidate.selected ? "مختارة" : candidate.qualified ? `مؤهلة · ${candidate.rejection_reason}` : "غير مؤهلة"}</small></div></div>)}</div></>}
    {tab === "decisions" && <><div className="field-group two-columns"><label className="field"><span>الرمز</span><select value={decisionSymbol} onChange={(event) => setDecisionSymbol(event.target.value)}><option value="">الكل</option>{Array.from(new Set((result.decisions ?? []).map((item) => item.symbol))).map((symbol) => <option key={symbol}>{symbol}</option>)}</select></label><label className="field"><span>الحدث</span><select value={decisionEvent} onChange={(event) => setDecisionEvent(event.target.value)}><option value="">الكل</option>{["evaluated", "selected", "rejected", "entered", "exited"].map((event) => <option key={event}>{event}</option>)}</select></label></div><div className="history-list">{filteredDecisions.map((decision) => <div className="history-row" key={decision.decision_id}><div><strong dir="ltr">{decision.symbol}</strong><small>{formatDateTime(decision.occurred_at)} · {decision.event} · {decision.qualified ? "مؤهل" : "غير مؤهل"} · {decision.selected ? "مختار" : "غير مختار"}</small></div><p>{decision.explanation_ar}</p></div>)}</div></>}
    {tab === "assumptions" && <><div className="review-callout"><strong dir="ltr">Config {stored.configuration_hash}</strong><p dir="ltr">Inputs {stored.input_data_hash ?? "pending"}</p></div><pre className="configuration-json" dir="ltr">{JSON.stringify(stored.request, null, 2)}</pre></>}
    {tab === "notes" && <div className="field-group"><div className="review-callout"><strong>فرضية قبل الاختبار</strong><p>{stored.request.pre_test_hypothesis || "لم تُسجل فرضية."}</p></div><label className="field"><span>ملاحظات بعد الاختبار</span><textarea value={notes} onChange={(event) => setNotes(event.target.value)} /></label><button className="primary-button" type="button" onClick={() => void updatePortfolioBacktestNotes(stored.backtest_id, notes).then(onChange)}>حفظ الملاحظة</button></div>}
  </section>;
}
function Result({ label, value }: { label: string; value: string }) { return <div className="backtest-metric"><span>{label}</span><strong>{value}</strong></div>; }

export function BotTradingPage() {
  const { state, refresh } = useWorkflowData();
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function act(
    deployment: BotDeployment,
    action: "start" | "monitor" | "pause" | "stop",
  ) {
    setBusy(deployment.deployment_id);
    setError(null);
    try {
      await transitionBotDeployment(deployment.deployment_id, action);
      await refresh();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "تعذر تحديث البوت.");
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="dashboard-content workflow-page">
      <PageHeader
        eyebrow="تنفيذ فعلي من نسخ ثابتة"
        title="التداول"
        description="يعرض البوتات المعتمدة وحالتها. المراكز والأوامر تبقى من المحرك وGate.io كمصدر حقيقة."
      />
      <Feedback message={error} error />
      <StateView value={state} unavailableLabel="تعذر تحميل البوتات">
        {(data) => data.deployments.length === 0 ? (
          <EmptyState
            title="لا توجد بوتات منشورة"
            description="اختبر إعداد العملة واعتمده، ثم أنشئ نسخة نشر من صفحة المراجعة."
          />
        ) : (
          <div className="deployment-grid">
            {data.deployments.map((deployment) => {
              const setup = data.setups.find((item) => item.setup_id === deployment.setup_id);
              const template = data.templates.find((item) => item.template_id === deployment.template_id);
              const active = deployment.status === "running" || deployment.status === "monitoring";
              return (
                <article className="panel deployment-card" key={deployment.deployment_id}>
                  <header>
                    <div>
                      <span className="eyebrow">{deployment.environment.toUpperCase()} · نسخة ثابتة</span>
                      <h2>{template?.name ?? deployment.strategy_type_id}</h2>
                      <p dir="ltr">{setup?.symbol ?? deploymentSymbol(deployment)}</p>
                    </div>
                    <StatusPill
                      label={deploymentStatusLabel(deployment.status)}
                      tone={active ? "positive" : deployment.status === "error" ? "negative" : "warning"}
                      pulse={active}
                    />
                  </header>
                  <div className="detail-facts-grid">
                    <ReviewFact label="نسخة الإعداد" value={`#${deployment.setup_revision}`} />
                    <ReviewFact label="نسخة الاستراتيجية" value={`#${deployment.template_revision}`} />
                    <ReviewFact label="إصدار المحرك" value={deployment.strategy_version} />
                    <ReviewFact label="أنشئ" value={formatDateTime(deployment.created_at)} />
                  </div>
                  {deployment.error_message && (
                    <div className="inline-alert error-alert">
                      <Icon name="alert" />
                      <span>{deployment.error_message}</span>
                    </div>
                  )}
                  <div className="deployment-actions">
                    {["not_started", "stopped"].includes(deployment.status) && (
                      <>
                        <button className="primary-button" type="button" disabled={busy !== null} onClick={() => void act(deployment, "start")}>
                          <Icon name="power" /> بدء التداول
                        </button>
                        <button className="secondary-button" type="button" disabled={busy !== null} onClick={() => void act(deployment, "monitor")}>
                          <Icon name="activity" /> بدء المراقبة
                        </button>
                      </>
                    )}
                    {active && (
                      <button className="secondary-button" type="button" disabled={busy !== null} onClick={() => void act(deployment, "pause")}>
                        <Icon name="power" /> إيقاف مؤقت
                      </button>
                    )}
                    {["running", "monitoring", "paused", "error"].includes(deployment.status) && (
                      <button className="danger-button" type="button" disabled={busy !== null} onClick={() => void act(deployment, "stop")}>
                        <Icon name="x" /> إيقاف
                      </button>
                    )}
                  </div>
                </article>
              );
            })}
          </div>
        )}
      </StateView>
    </div>
  );
}

export function PerformancePage({ environment }: { environment: Environment }) {
  const [state, setState] = useState<RemoteData<AccountPerformanceSeries>>({ status: "loading" });
  const [period, setPeriod] = useState<"today" | "7d" | "30d" | "all">("30d");
  useEffect(() => { const controller = new AbortController(); setState({ status: "loading" }); loadAccountPerformance(environment, period, controller.signal).then((data) => setState({ status: "ready", data })).catch((error) => { if (!(error instanceof DOMException && error.name === "AbortError")) setState({ status: "error", message: error instanceof Error ? error.message : "تعذر تحميل الأداء." }); }); return () => controller.abort(); }, [environment, period]);
  return <div className="dashboard-content workflow-page"><PageHeader eyebrow="حساب التنفيذ فقط" title="الأداء" description="P&L والحقوق والرسوم والتمويل من Paper أو Gate.io. نتائج الاختبارات التاريخية لا تختلط بهذه الأرقام." action={<select value={period} onChange={(event) => setPeriod(event.target.value as typeof period)}><option value="today">اليوم</option><option value="7d">7 أيام</option><option value="30d">30 يوماً</option><option value="all">الكل</option></select>} /><StateView value={state} unavailableLabel="تعذر تحميل الأداء">{(data) => <><div className="summary-grid"><PerformanceCard label="تغير الحقوق" value={formatMoney(data.equity_change)} /><PerformanceCard label="نسبة التغير" value={formatPercent(data.equity_change_percentage)} /><PerformanceCard label="P&L المحقق" value={formatMoney(data.realized_pnl_total)} /><PerformanceCard label="P&L غير المحقق" value={formatMoney(data.unrealized_pnl)} /><PerformanceCard label="الرسوم" value={formatMoney(data.fees_total)} /><PerformanceCard label="التمويل" value={formatMoney(data.funding_total)} /><PerformanceCard label="صافي P&L" value={formatMoney(data.net_pnl_total)} /><PerformanceCard label="أقصى تراجع" value={formatPercent(data.maximum_drawdown_percentage)} /></div><section className="panel performance-ledger-panel"><div className="panel-header"><div><h2>منحنى الحقوق</h2><p>{environment.toUpperCase()} · {data.points.length} نقطة من دفتر المحرك.</p></div></div><SimpleEquityCurve data={data} /></section></>}</StateView></div>;
}
function PerformanceCard({ label, value }: { label: string; value: string }) { return <article className="summary-card"><div className="summary-icon"><Icon name="chart" /></div><div><span>{label}</span><strong>{value}</strong><small>المصدر: المحرك</small></div></article>; }
function SimpleEquityCurve({ data }: { data: AccountPerformanceSeries }) { if (data.points.length < 2) return <EmptyState title="لا توجد نقاط كافية" description="سيظهر المنحنى بعد تسجيل أكثر من نقطة حقوق." />; const values = data.points.map((point) => Number(point.total_equity)); const min = Math.min(...values); const max = Math.max(...values); const range = max - min || 1; const points = values.map((value, index) => `${(index / (values.length - 1)) * 100},${56 - ((value - min) / range) * 48}`).join(" "); return <figure className="equity-curve"><figcaption><strong>{formatMoney(min)} — {formatMoney(max)}</strong><span>{formatDateTime(data.points[0].occurred_at)} — {formatDateTime(data.points.at(-1)?.occurred_at)}</span></figcaption><svg viewBox="0 0 100 60" preserveAspectRatio="none" role="img" aria-label="منحنى حقوق الحساب"><polyline points={points} /></svg></figure>; }

function timeframeText(minutes: number): string { if (minutes % 1440 === 0) return `${minutes / 1440} يوم`; if (minutes % 60 === 0) return `${minutes / 60} ساعة`; return `${minutes} دقيقة`; }
function equalPercentageAllocations(count: number): string[] {
  const precision = 1_000_000;
  const totalUnits = 100 * precision;
  const baseUnits = Math.floor(totalUnits / count);
  return Array.from({ length: count }, (_, index) => {
    const units = index === count - 1
      ? totalUnits - baseUnits * (count - 1)
      : baseUnits;
    return (units / precision).toFixed(6);
  });
}
function setupStatusLabel(status: StrategyCoinSetup["status"]): string { return ({ draft: "مسودة", ready_for_backtest: "جاهز للاختبار", backtest_required: "يلزم اختبار جديد", backtest_failed: "لم يجتز الاختبار", backtest_passed: "اجتاز الاختبار", approved_paper: "معتمد Paper", approved_testnet: "معتمد Testnet", approved_live: "معتمد Live", archived: "مؤرشف" })[status]; }
function opportunityStatusLabel(status: StrategyOpportunity["status"]): string { return ({ new: "جديدة", reviewed: "تمت المراجعة", approved: "مقبولة", rejected: "مرفوضة", ignored: "متجاهلة", expired: "منتهية", converted: "تحولت إلى إعداد" })[status]; }
function buildConfigurationOverrides(
  inherited: Record<string, JsonValue>,
  effective: Record<string, JsonValue>,
): Record<string, JsonValue> {
  return Object.fromEntries(
    Object.entries(effective).filter(([key, value]) => (
      JSON.stringify(inherited[key]) !== JSON.stringify(value)
    )),
  );
}
function deploymentStatusLabel(status: BotDeployment["status"]): string { return ({ not_started: "لم يبدأ", starting: "يبدأ", running: "يتداول", monitoring: "يراقب", paused: "متوقف مؤقتاً", stopped: "متوقف", error: "خطأ" })[status]; }
function deploymentSymbol(deployment: BotDeployment): string {
  const value = deployment.configuration_snapshot.symbol;
  return typeof value === "string" ? value : "—";
}
function assessmentLabel(label: StoredBacktestRun["result"]["assessment"]["label"]): string { return ({ promising: "واعدة", mixed: "مختلطة", weak: "ضعيفة", insufficient_data: "بيانات غير كافية" })[label]; }
