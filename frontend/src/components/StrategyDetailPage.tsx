import { useEffect, useMemo, useState } from "react";

import {
  deleteStrategy,
  duplicateStrategy,
  loadStrategyConfigurationVersions,
  loadStrategyDecisions,
  loadStrategyRuns,
  loadTradeHistory,
  loadTradeHistorySummary,
  transitionStrategy,
  updateStrategy,
} from "../api";
import {
  directionLabel,
  formatDateTime,
  formatDecimal,
  formatDuration,
  formatMoney,
  formatPercent,
  strategyStatusLabel,
} from "../lib/format";
import type {
  JsonValue,
  RemoteData,
  StrategyConfigurationVersion,
  StrategyDecision,
  StrategyInstance,
  StrategyRun,
  StrategyTypeMetadata,
  TradeFill,
  TradeHistorySummary,
} from "../types";
import { Icon } from "./Icon";
import { StateView, StatusPill } from "./StateView";
import { StrategyChart } from "./StrategyChart";
import {
  normalizeFixedPriceLadderLevels,
  StrategyConfigurationFields,
  validateFixedPriceLadderLevels,
} from "./StrategyConfigurationFields";

interface StrategyDetailPageProps {
  strategy: StrategyInstance;
  metadata: StrategyTypeMetadata | null;
  onBack: () => void;
  onOpenDiscovery: () => void;
  onChanged: (strategy: StrategyInstance) => void;
  onDeleted: (instanceId: string) => void;
}

type DetailTab = "overview" | "configuration" | "history";

type Feedback = { tone: "success" | "warning" | "error"; message: string } | null;

export function StrategyDetailPage({
  strategy,
  metadata,
  onBack,
  onOpenDiscovery,
  onChanged,
  onDeleted,
}: StrategyDetailPageProps) {
  const [tab, setTab] = useState<DetailTab>("overview");
  const [editing, setEditing] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);
  const [feedback, setFeedback] = useState<Feedback>(null);
  const [decisions, setDecisions] = useState<RemoteData<StrategyDecision[]>>({ status: "loading" });
  const [runs, setRuns] = useState<RemoteData<StrategyRun[]>>({ status: "loading" });
  const [versions, setVersions] = useState<RemoteData<StrategyConfigurationVersion[]>>({ status: "loading" });
  const [tradeSummary, setTradeSummary] = useState<RemoteData<TradeHistorySummary>>({ status: "loading" });
  const [tradeFills, setTradeFills] = useState<RemoteData<TradeFill[]>>({ status: "loading" });
  const [name, setName] = useState(strategy.name);
  const [environment, setEnvironment] = useState(strategy.environment);
  const [symbol, setSymbol] = useState(strategy.symbol);
  const [timeframe, setTimeframe] = useState(strategy.timeframe_minutes);
  const [direction, setDirection] = useState(strategy.direction);
  const [requestedMargin, setRequestedMargin] = useState(strategy.requested_margin);
  const [requestedLeverage, setRequestedLeverage] = useState(strategy.requested_leverage);
  const [configuration, setConfiguration] = useState<Record<string, JsonValue>>(strategy.configuration);

  const canEdit = strategy.status === "stopped" || strategy.status === "paused";
  const latestDecision = decisions.status === "ready" ? decisions.data[0] ?? null : null;
  const activeRun = runs.status === "ready" ? runs.data.find((run) => run.status === "active") ?? null : null;
  const runDuration = activeRun
    ? formatDuration(Math.max(0, Date.now() - new Date(activeRun.started_at).getTime()) / 1000)
    : "—";

  const analysisRows = useMemo(() => {
    if (!latestDecision) {
      return [];
    }
    return Object.entries(latestDecision.analysis).map(([key, value]) => {
      const field = metadata?.live_analysis_fields.find((item) => item.key === key);
      return {
        key,
        label: field?.label_ar ?? key,
        value: displayValue(value, field?.unit),
      };
    });
  }, [latestDecision, metadata]);

  useEffect(() => {
    setName(strategy.name);
    setEnvironment(strategy.environment);
    setSymbol(strategy.symbol);
    setTimeframe(strategy.timeframe_minutes);
    setDirection(strategy.direction);
    setRequestedMargin(strategy.requested_margin);
    setRequestedLeverage(strategy.requested_leverage);
    setConfiguration(strategy.configuration);
    setEditing(false);
    setFeedback(null);
  }, [strategy]);

  useEffect(() => {
    const controller = new AbortController();
    setDecisions({ status: "loading" });
    setRuns({ status: "loading" });
    setVersions({ status: "loading" });
    setTradeSummary({ status: "loading" });
    setTradeFills({ status: "loading" });
    Promise.all([
      loadStrategyDecisions(strategy.instance_id, controller.signal),
      loadStrategyRuns(strategy.instance_id, controller.signal),
      loadStrategyConfigurationVersions(strategy.instance_id, controller.signal),
      loadTradeHistorySummary({ instanceId: strategy.instance_id }, controller.signal),
      loadTradeHistory({ instanceId: strategy.instance_id, limit: 20 }, controller.signal),
    ])
      .then(([decisionData, runData, versionData, summaryData, fillData]) => {
        setDecisions({ status: "ready", data: decisionData });
        setRuns({ status: "ready", data: runData });
        setVersions({ status: "ready", data: versionData });
        setTradeSummary({ status: "ready", data: summaryData });
        setTradeFills({ status: "ready", data: fillData });
      })
      .catch((error) => {
        if (error instanceof DOMException && error.name === "AbortError") {
          return;
        }
        const message = error instanceof Error ? error.message : "تعذر تحميل سجل الاستراتيجية.";
        setDecisions({ status: "error", message });
        setRuns({ status: "error", message });
        setVersions({ status: "error", message });
        setTradeSummary({ status: "error", message });
        setTradeFills({ status: "error", message });
      });
    return () => controller.abort();
  }, [strategy.instance_id, strategy.revision]);

  async function handleLifecycle(action: "start" | "monitor" | "pause" | "stop") {
    setBusy(action);
    setFeedback(null);
    try {
      const updated = await transitionStrategy(strategy.instance_id, action);
      onChanged(updated);
      setFeedback({ tone: "success", message: "حُدثت حالة الاستراتيجية بعد تأكيد المحرك." });
    } catch (error) {
      setFeedback({
        tone: "error",
        message: error instanceof Error ? error.message : "تعذر تحديث حالة الاستراتيجية.",
      });
    } finally {
      setBusy(null);
    }
  }

  async function handleSave() {
    if (!canEdit) {
      setFeedback({ tone: "warning", message: "أوقف الاستراتيجية أو أوقفها مؤقتاً قبل تعديل الإعدادات." });
      return;
    }
    if (strategy.type_id === "fixed_price_ladder") {
      const ladderError = validateFixedPriceLadderLevels(configuration.levels);
      if (ladderError) {
        setFeedback({ tone: "error", message: ladderError });
        return;
      }
    }
    setBusy("save");
    setFeedback(null);
    try {
      const updated = await updateStrategy(strategy.instance_id, {
        name: name.trim(),
        environment,
        symbol: symbol.trim().toUpperCase().replace("/", "_"),
        timeframe_minutes: timeframe,
        direction,
        requested_margin: requestedMargin,
        requested_leverage: requestedLeverage,
        configuration: strategy.type_id === "fixed_price_ladder"
          ? {
              ...configuration,
              levels: normalizeFixedPriceLadderLevels(configuration.levels),
            }
          : configuration,
      });
      onChanged(updated);
      setEditing(false);
      setFeedback({ tone: "success", message: "حفظ المحرك الإعدادات وأنشأ نسخة تكوين جديدة." });
    } catch (error) {
      setFeedback({
        tone: "error",
        message: error instanceof Error ? error.message : "تعذر حفظ إعدادات الاستراتيجية.",
      });
    } finally {
      setBusy(null);
    }
  }

  async function handleDuplicate() {
    const requestedName = window.prompt("اسم النسخة الجديدة", `${strategy.name} — نسخة`);
    if (requestedName === null) {
      return;
    }
    setBusy("duplicate");
    setFeedback(null);
    try {
      const duplicate = await duplicateStrategy(strategy.instance_id, requestedName.trim() || undefined);
      onChanged(duplicate);
      setFeedback({ tone: "success", message: `أُنشئت النسخة «${duplicate.name}» بحالة متوقفة.` });
    } catch (error) {
      setFeedback({
        tone: "error",
        message: error instanceof Error ? error.message : "تعذر نسخ الاستراتيجية.",
      });
    } finally {
      setBusy(null);
    }
  }

  async function handleDelete() {
    const confirmed = window.confirm(
      `حذف «${strategy.name}»؟ يرفض المحرك الحذف إذا كانت الاستراتيجية نشطة أو تملك أمراً أو مركزاً مسجلاً.`,
    );
    if (!confirmed) {
      return;
    }
    setBusy("delete");
    setFeedback(null);
    try {
      await deleteStrategy(strategy.instance_id);
      onDeleted(strategy.instance_id);
    } catch (error) {
      setFeedback({
        tone: "error",
        message: error instanceof Error ? error.message : "تعذر حذف الاستراتيجية.",
      });
      setBusy(null);
    }
  }

  function updateConfiguration(key: string, value: JsonValue) {
    setConfiguration((current) => ({ ...current, [key]: value }));
  }

  return (
    <div className="strategy-page dashboard-content">
      <header className="strategy-page-header">
        <div className="strategy-page-heading">
          <button className="back-button" type="button" onClick={onBack}>
            <Icon name="chevron" />
            العودة إلى لوحة العمليات
          </button>
          <div className="strategy-title-line">
            <div>
              <h1>{strategy.name}</h1>
              <p>{metadata?.display_name_ar ?? strategy.type_id} · الإصدار {metadata?.version ?? "—"}</p>
            </div>
            <StatusPill label={strategyStatusLabel(strategy.status)} tone={statusTone(strategy.status)} />
          </div>
        </div>
        <div className="strategy-control-bar" aria-label="تحكم الاستراتيجية">
          {metadata?.supports_scanning && metadata.supports_backtesting && (
            <button className="secondary-button" type="button" disabled={busy !== null} onClick={onOpenDiscovery}>
              <Icon name="activity" />
              فحص السوق واختبار العملات
            </button>
          )}
          {(strategy.status === "stopped" || strategy.status === "paused") && (
            <button className="primary-button" type="button" disabled={busy !== null} onClick={() => void handleLifecycle("start")}>
              <Icon name="power" />
              {busy === "start" ? "جارٍ البدء…" : "بدء التداول"}
            </button>
          )}
          {(strategy.status === "stopped" || strategy.status === "paused") && metadata?.supports_monitoring && (
            <button className="secondary-button" type="button" disabled={busy !== null} onClick={() => void handleLifecycle("monitor")}>
              <Icon name="activity" />
              {busy === "monitor" ? "جارٍ البدء…" : "بدء المراقبة"}
            </button>
          )}
          {(strategy.status === "running" || strategy.status === "monitoring") && (
            <button className="secondary-button" type="button" disabled={busy !== null} onClick={() => void handleLifecycle("pause")}>
              <Icon name="power" />
              {busy === "pause" ? "جارٍ الإيقاف…" : "إيقاف مؤقت"}
            </button>
          )}
          {strategy.status !== "stopped" && (
            <button className="danger-button" type="button" disabled={busy !== null} onClick={() => void handleLifecycle("stop")}>
              <Icon name="x" />
              {busy === "stop" ? "جارٍ الإيقاف…" : "إيقاف"}
            </button>
          )}
        </div>
      </header>

      {feedback && (
        <div className={`inline-alert ${feedback.tone}-alert`} role={feedback.tone === "error" ? "alert" : "status"}>
          <Icon name={feedback.tone === "success" ? "shield" : "alert"} />
          <span>{feedback.message}</span>
        </div>
      )}

      <nav className="detail-tabs" aria-label="أقسام الاستراتيجية">
        <button className={tab === "overview" ? "active" : ""} type="button" onClick={() => setTab("overview")}>نظرة عامة وتحليل</button>
        <button className={tab === "configuration" ? "active" : ""} type="button" onClick={() => setTab("configuration")}>الإعدادات</button>
        <button className={tab === "history" ? "active" : ""} type="button" onClick={() => setTab("history")}>السجل والأداء</button>
      </nav>

      {tab === "overview" && (
        <div className="strategy-detail-layout">
          <section className="panel strategy-overview-panel">
            <div className="panel-header"><div><h2>الحالة التشغيلية</h2><p>القيم الأساسية المسجلة في المحرك.</p></div></div>
            <div className="detail-facts-grid">
              <DetailFact label="البيئة" value={strategy.environment.toUpperCase()} />
              <DetailFact label="العقد" value={strategy.symbol} mono />
              <DetailFact label="الإطار" value={`${strategy.timeframe_minutes} دقيقة`} />
              <DetailFact label="الاتجاه" value={directionLabel(strategy.direction)} />
              <DetailFact label="مدة التشغيل الحالية" value={runDuration} />
              <DetailFact label="نسخة الإعداد" value={`#${strategy.revision}`} mono />
              <DetailFact label="آخر تحديث" value={formatDateTime(strategy.updated_at)} />
              <DetailFact label="آخر قرار" value={latestDecision ? formatDateTime(latestDecision.occurred_at) : "لا يوجد"} />
            </div>
          </section>

          <section className="panel live-analysis-panel">
            <div className="panel-header">
              <div><h2>التحليل الحي</h2><p>لماذا تمر أو تفشل شروط الاستراتيجية.</p></div>
              {latestDecision && <StatusPill label={latestDecision.eligible ? "مؤهلة" : "غير مؤهلة"} tone={latestDecision.eligible ? "positive" : "warning"} />}
            </div>
            <StateView value={decisions} unavailableLabel="تعذر تحميل قرارات الاستراتيجية">
              {(items) => items.length === 0 ? (
                <div className="analysis-empty">لم يسجل المحرك قراراً لهذه الاستراتيجية بعد.</div>
              ) : (
                <div className="analysis-stack">
                  <div className="decision-banner">
                    <span>القرار النهائي</span>
                    <strong>{latestDecision?.signal ?? "—"}</strong>
                    <small>{latestDecision?.reason_codes.join(" · ") || "لا توجد أسباب مسجلة"}</small>
                  </div>
                  <div className="analysis-rows">
                    {analysisRows.map((row) => (
                      <div className="analysis-row" key={row.key}>
                        <span>{row.label}</span>
                        <strong>{row.value}</strong>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </StateView>
          </section>

          <div className="strategy-chart-wrap">
            <StrategyChart
              strategy={strategy}
              metadata={metadata}
              decision={latestDecision}
            />
          </div>

          <section className="panel strategy-warning-panel">
            <div className="panel-header"><div><h2>قدرات وتحذيرات النوع</h2></div></div>
            <p>{metadata?.description_ar ?? "لا توجد معلومات وصفية متاحة لهذا النوع."}</p>
            <div className="capability-row">
              <span>{metadata?.supports_automatic_trading ? "يدعم التداول التلقائي" : "لا يدعم التداول التلقائي"}</span>
              <span>{metadata?.supports_monitoring ? "يدعم المراقبة" : "لا يدعم المراقبة"}</span>
            </div>
            {(metadata?.important_warnings_ar.length ?? 0) > 0 && (
              <ul className="warning-list">
                {metadata?.important_warnings_ar.map((warning) => <li key={warning}>{warning}</li>)}
              </ul>
            )}
          </section>
        </div>
      )}

      {tab === "configuration" && (
        <section className="panel strategy-config-panel">
          <div className="panel-header">
            <div><h2>إعدادات النسخة المحفوظة</h2><p>التحقق النهائي يتم داخل المحرك قبل الالتزام.</p></div>
            <button className="secondary-button" type="button" disabled={!canEdit || busy !== null} onClick={() => setEditing((value) => !value)}>
              <Icon name="settings" />
              {editing ? "إلغاء التعديل" : "تعديل"}
            </button>
          </div>
          {!canEdit && (
            <div className="inline-alert warning-alert" role="note">
              <Icon name="alert" />
              <span>الإعدادات للقراءة فقط أثناء التشغيل أو المراقبة.</span>
            </div>
          )}
          <div className="field-group two-columns">
            <label className="field"><span>الاسم</span><input disabled={!editing} value={name} onChange={(event) => setName(event.target.value)} /></label>
            <label className="field"><span>العقد</span><input disabled={!editing} value={symbol} onChange={(event) => setSymbol(event.target.value)} /></label>
          </div>
          <div className="field-group three-columns">
            <label className="field"><span>البيئة</span><select disabled={!editing} value={environment} onChange={(event) => setEnvironment(event.target.value as StrategyInstance["environment"])}><option value="live">Live</option><option value="testnet">Testnet</option><option value="paper">Paper</option></select></label>
            <label className="field"><span>الإطار بالدقائق</span><input disabled={!editing} min={1} max={10080} type="number" value={timeframe} onChange={(event) => setTimeframe(Number(event.target.value))} /></label>
            <label className="field"><span>الاتجاه</span><select disabled={!editing} value={direction} onChange={(event) => setDirection(event.target.value as StrategyInstance["direction"])}><option value="both">الاتجاهان</option><option value="long">شراء فقط</option><option value="short">بيع فقط</option></select></label>
          </div>
          <div className="field-group two-columns">
            <label className="field"><span>الهامش لكل دخول تلقائي</span><input disabled={!editing} min="0.01" step="0.01" inputMode="decimal" value={requestedMargin} onChange={(event) => setRequestedMargin(event.target.value)} /></label>
            <label className="field"><span>الرافعة المطلوبة</span><input disabled={!editing} min={1} max={100} type="number" value={requestedLeverage} onChange={(event) => setRequestedLeverage(Number(event.target.value))} /></label>
          </div>
          <p className="field-help">المحرك وحده يحول هذه القيم إلى كمية عقد بعد التحقق من المخاطر والرصيد وقواعد Gate.io.</p>
          <StrategyConfigurationFields
            disabled={!editing}
            metadata={metadata}
            configuration={configuration}
            onChange={updateConfiguration}
          />
          {editing && (
            <div className="form-actions">
              <button className="primary-button" type="button" disabled={busy !== null || !name.trim() || !symbol.trim()} onClick={() => void handleSave()}>
                <Icon name="shield" />
                {busy === "save" ? "جارٍ الحفظ…" : "حفظ في المحرك"}
              </button>
            </div>
          )}
          <div className="strategy-admin-actions">
            <button className="secondary-button" type="button" disabled={busy !== null} onClick={() => void handleDuplicate()}>
              <Icon name="plus" />
              {busy === "duplicate" ? "جارٍ النسخ…" : "نسخ الاستراتيجية"}
            </button>
            <button className="danger-button" type="button" disabled={busy !== null || strategy.status !== "stopped"} onClick={() => void handleDelete()}>
              <Icon name="x" />
              {busy === "delete" ? "جارٍ الحذف…" : "حذف الاستراتيجية"}
            </button>
          </div>
        </section>
      )}

      {tab === "history" && (
        <div className="strategy-history-layout">
          <section className="panel strategy-performance-panel">
            <div className="panel-header"><div><h2>أداء التنفيذ المنسوب</h2><p>محسوب داخل المحرك من الصفقات التي احتفظت بملكية هذه الاستراتيجية وقت التنفيذ.</p></div></div>
            <StateView value={tradeSummary} unavailableLabel="تعذر تحميل أداء التنفيذ">
              {(summary) => (
                <div className="strategy-performance-grid">
                  <DetailFact label="التنفيذات" value={String(summary.fills)} />
                  <DetailFact label="الرابحة" value={String(summary.winning_fills)} />
                  <DetailFact label="الخاسرة" value={String(summary.losing_fills)} />
                  <DetailFact label="نسبة الفوز" value={formatPercent(summary.win_rate_percentage)} />
                  <DetailFact label="الصافي المحقق" value={formatMoney(summary.realized_pnl)} />
                  <DetailFact label="الربح الإجمالي" value={formatMoney(summary.gross_profit)} />
                  <DetailFact label="الخسارة الإجمالية" value={formatMoney(summary.gross_loss)} />
                  <DetailFact label="عامل الربح" value={formatDecimal(summary.profit_factor)} />
                  <DetailFact label="متوسط الربح" value={formatMoney(summary.average_win)} />
                  <DetailFact label="متوسط الخسارة" value={formatMoney(summary.average_loss)} />
                  <DetailFact label="الرسوم / الحسومات" value={formatMoney(summary.fees)} />
                  <DetailFact label="تغطية النتيجة المحققة" value={`${summary.realized_pnl_known_fills} / ${summary.fills}`} />
                </div>
              )}
            </StateView>
          </section>
          <section className="panel strategy-fill-history-panel">
            <div className="panel-header"><div><h2>آخر التنفيذات</h2><p>آخر 20 تعبئة مرتبطة بهذه الاستراتيجية أو إحدى فترات تشغيلها.</p></div></div>
            <StateView value={tradeFills} unavailableLabel="تعذر تحميل التنفيذات">
              {(items) => items.length === 0 ? <div className="analysis-empty">لا توجد صفقات منفذة منسوبة لهذه الاستراتيجية بعد.</div> : (
                <div className="history-list">{items.map((fill) => <div className="history-row" key={`${fill.environment}-${fill.external_trade_id}`}><div><strong>{fill.contract} · {tradeEffectLabel(fill)}</strong><small>{formatDateTime(fill.occurred_at)} · {formatDecimal(fill.quantity)} @ {formatDecimal(fill.price)}</small></div><div><strong>{fill.realized_pnl === null ? "النتيجة غير متاحة" : formatMoney(fill.realized_pnl)}</strong><small>{fill.environment.toUpperCase()} · {fill.role}</small></div></div>)}</div>
              )}
            </StateView>
          </section>
          <section className="panel">
            <div className="panel-header"><div><h2>فترات التشغيل</h2><p>كل فترة تداول أو مراقبة مسجلة.</p></div></div>
            <StateView value={runs} unavailableLabel="تعذر تحميل فترات التشغيل">
              {(items) => items.length === 0 ? <div className="analysis-empty">لا توجد فترات تشغيل بعد.</div> : (
                <div className="history-list">{items.map((run) => <div className="history-row" key={run.run_id}><div><strong>{run.mode === "automatic" ? "تداول تلقائي" : "مراقبة"}</strong><small>{formatDateTime(run.started_at)}</small></div><div><StatusPill label={run.status === "active" ? "نشطة" : run.status === "error" ? "خطأ" : "مكتملة"} tone={run.status === "active" ? "positive" : run.status === "error" ? "negative" : "neutral"} /><small>{run.end_reason ?? "—"}</small></div></div>)}</div>
              )}
            </StateView>
          </section>
          <section className="panel">
            <div className="panel-header"><div><h2>نسخ الإعداد</h2><p>سجل غير قابل للتعديل لكل حفظ.</p></div></div>
            <StateView value={versions} unavailableLabel="تعذر تحميل نسخ الإعداد">
              {(items) => items.length === 0 ? <div className="analysis-empty">لا توجد نسخ إعداد.</div> : (
                <div className="history-list">{items.slice().reverse().map((version) => <div className="history-row" key={version.version_id}><div><strong>الإصدار #{version.revision}</strong><small>{formatDateTime(version.created_at)}</small></div><code>{Object.keys(version.configuration).length} حقول</code></div>)}</div>
              )}
            </StateView>
          </section>
        </div>
      )}
    </div>
  );
}

function DetailFact({ label, value, mono = false }: { label: string; value: string; mono?: boolean }) {
  return <div className="detail-fact"><span>{label}</span><strong className={mono ? "numeric" : undefined}>{value}</strong></div>;
}

function tradeEffectLabel(fill: TradeFill): string {
  if (fill.position_effect === "close") {
    return fill.side === "sell" ? "إغلاق Long" : "إغلاق Short";
  }
  if (fill.position_effect === "mixed") return "إغلاق وفتح";
  return fill.side === "buy" ? "فتح Long" : "فتح Short";
}

function statusTone(status: StrategyInstance["status"]): "positive" | "warning" | "negative" | "neutral" {
  if (status === "running") return "positive";
  if (status === "monitoring" || status === "paused") return "warning";
  if (status === "error") return "negative";
  return "neutral";
}

function displayValue(value: JsonValue, unit?: string | null): string {
  let text: string;
  if (value === null) text = "غير متاح";
  else if (typeof value === "boolean") text = value ? "نعم" : "لا";
  else if (typeof value === "object") text = JSON.stringify(value);
  else text = String(value);
  return unit ? `${text} ${unit}` : text;
}
