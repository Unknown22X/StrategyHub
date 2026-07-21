import { useEffect, useMemo, useState } from "react";

import {
  createStrategyFromBacktest,
  listBacktests,
  listDiscoveryScans,
  runBacktest,
  runDiscoveryScan,
} from "../api";
import {
  formatDateTime,
  formatDecimal,
  formatMoney,
  formatPercent,
} from "../lib/format";
import type {
  BacktestEquityPoint,
  BacktestStrategyCreateRequest,
  Environment,
  JsonValue,
  StoredBacktestRun,
  StoredStrategyScan,
  StrategyInstance,
  StrategyScanCandidate,
  StrategyTypeMetadata,
} from "../types";
import { Icon } from "./Icon";
import {
  StrategyConfigurationFields,
  strategySchemaDefaults,
} from "./StrategyConfigurationFields";
import { EmptyState, StatusPill } from "./StateView";

interface DiscoveryLabPageProps {
  strategyTypes: StrategyTypeMetadata[];
  environment: Environment | null;
  initialStrategy?: StrategyInstance | null;
  onBack: () => void;
  onStrategyCreated: (strategy: StrategyInstance) => void;
}

type BusyAction = "scan" | "backtest" | "apply" | null;
type Feedback = { tone: "success" | "warning" | "error"; message: string } | null;

const periodOptions = [
  { days: 30, label: "30 يوماً" },
  { days: 90, label: "90 يوماً" },
  { days: 180, label: "180 يوماً" },
  { days: 365, label: "سنة" },
];

const assessmentLabels: Record<StoredBacktestRun["result"]["assessment"]["label"], string> = {
  promising: "واعدة",
  mixed: "مختلطة",
  weak: "ضعيفة",
  insufficient_data: "بيانات غير كافية",
};

export function DiscoveryLabPage({
  strategyTypes,
  environment,
  initialStrategy,
  onBack,
  onStrategyCreated,
}: DiscoveryLabPageProps) {
  const availableTypes = useMemo(
    () => strategyTypes.filter((item) => item.supports_scanning && item.supports_backtesting),
    [strategyTypes],
  );
  const initialTypeId = initialStrategy?.type_id
    ?? availableTypes[0]?.type_id
    ?? "";
  const [selectedTypeId, setSelectedTypeId] = useState(initialTypeId);
  const metadata = useMemo(
    () => availableTypes.find((item) => item.type_id === selectedTypeId) ?? null,
    [availableTypes, selectedTypeId],
  );
  const [configuration, setConfiguration] = useState<Record<string, JsonValue>>(
    initialStrategy?.configuration
      ?? (availableTypes[0] ? strategySchemaDefaults(availableTypes[0]) : {}),
  );
  const [timeframe, setTimeframe] = useState(
    initialStrategy?.timeframe_minutes
      ?? availableTypes[0]?.supported_timeframes[0]
      ?? 15,
  );
  const [minimumVolume, setMinimumVolume] = useState("1000000");
  const [maximumSymbols, setMaximumSymbols] = useState(30);
  const [maximumCandidates, setMaximumCandidates] = useState(15);
  const [minimumScore, setMinimumScore] = useState(35);
  const [scan, setScan] = useState<StoredStrategyScan | null>(null);
  const [selectedSymbol, setSelectedSymbol] = useState<string | null>(null);
  const [periodDays, setPeriodDays] = useState(90);
  const [initialBalance, setInitialBalance] = useState("1000");
  const [marginPerTrade, setMarginPerTrade] = useState("100");
  const [leverage, setLeverage] = useState(3);
  const [feeRate, setFeeRate] = useState("0.0005");
  const [slippageBps, setSlippageBps] = useState("5");
  const [minimumTrades, setMinimumTrades] = useState(20);
  const [backtest, setBacktest] = useState<StoredBacktestRun | null>(null);
  const [recentScans, setRecentScans] = useState<StoredStrategyScan[]>([]);
  const [recentBacktests, setRecentBacktests] = useState<StoredBacktestRun[]>([]);
  const [strategyName, setStrategyName] = useState("");
  const [busy, setBusy] = useState<BusyAction>(null);
  const [feedback, setFeedback] = useState<Feedback>(null);

  const selectedCandidate = useMemo(
    () => scan?.result.candidates.find((candidate) => candidate.symbol === selectedSymbol)
      ?? scan?.result.candidates[0]
      ?? null,
    [scan, selectedSymbol],
  );

  async function refreshResearchHistory() {
    try {
      const [scans, backtests] = await Promise.all([
        listDiscoveryScans(),
        listBacktests(),
      ]);
      setRecentScans(scans.slice(0, 8));
      setRecentBacktests(backtests.slice(0, 8));
    } catch {
      // The current research flow remains usable when historical listing is unavailable.
    }
  }

  useEffect(() => {
    void refreshResearchHistory();
  }, []);

  useEffect(() => {
    if (selectedTypeId) return;
    const fallbackType = availableTypes[0];
    if (!fallbackType) return;
    setSelectedTypeId(initialStrategy?.type_id ?? fallbackType.type_id);
  }, [availableTypes, initialStrategy?.type_id, selectedTypeId]);

  useEffect(() => {
    if (!metadata) return;
    const seeded = initialStrategy?.type_id === metadata.type_id
      ? initialStrategy.configuration
      : strategySchemaDefaults(metadata);
    setConfiguration(seeded);
    setTimeframe(
      initialStrategy?.type_id === metadata.type_id
        ? initialStrategy.timeframe_minutes
        : metadata.supported_timeframes[0] ?? 15,
    );
    setScan(null);
    setSelectedSymbol(null);
    setBacktest(null);
    setFeedback(null);
  }, [metadata?.type_id]);

  useEffect(() => {
    if (selectedCandidate && !strategyName) {
      setStrategyName(`${selectedCandidate.symbol} — ${metadata?.display_name_ar ?? "استراتيجية"}`);
    }
  }, [metadata?.display_name_ar, selectedCandidate?.symbol]);

  async function handleScan() {
    if (!metadata) {
      setFeedback({ tone: "error", message: "لا توجد استراتيجية قابلة للفحص." });
      return;
    }
    setBusy("scan");
    setFeedback(null);
    setBacktest(null);
    try {
      const result = await runDiscoveryScan({
        strategy_type_id: metadata.type_id,
        timeframe_minutes: timeframe,
        configuration,
        minimum_quote_volume: minimumVolume || "0",
        maximum_symbols: maximumSymbols,
        maximum_candidates: maximumCandidates,
        minimum_score: minimumScore,
      });
      setScan(result);
      setSelectedSymbol(result.result.candidates[0]?.symbol ?? null);
      setStrategyName("");
      void refreshResearchHistory();
      setFeedback({
        tone: result.result.candidates.length > 0 ? "success" : "warning",
        message: result.result.candidates.length > 0
          ? `اكتمل الفحص وسجل المحرك ${result.result.candidates.length} مرشحاً قابلاً للمراجعة.`
          : "اكتمل الفحص ولم تتجاوز أي عملة الحد المطلوب.",
      });
    } catch (error) {
      setFeedback({
        tone: "error",
        message: error instanceof Error ? error.message : "تعذر فحص سوق Gate.io.",
      });
    } finally {
      setBusy(null);
    }
  }

  async function handleBacktest() {
    if (!scan || !selectedCandidate) return;
    if (!selectedCandidate.backtest_ready) {
      setFeedback({
        tone: "warning",
        message: "لا يملك هذا المرشح عدداً كافياً من الشموع المكتملة للاختبار.",
      });
      return;
    }
    const end = new Date(selectedCandidate.evaluated_at);
    const start = new Date(end);
    start.setUTCDate(start.getUTCDate() - periodDays);
    setBusy("backtest");
    setFeedback(null);
    try {
      const result = await runBacktest({
        scan_id: scan.scan_id,
        strategy_type_id: scan.request.strategy_type_id,
        symbol: selectedCandidate.symbol,
        timeframe_minutes: scan.request.timeframe_minutes,
        configuration: scan.request.configuration,
        start: start.toISOString(),
        end: end.toISOString(),
        settings: {
          initial_balance: initialBalance,
          margin_per_trade: marginPerTrade,
          leverage,
          taker_fee_rate: feeRate,
          slippage_basis_points: slippageBps,
          default_take_profit_percentage: "5",
          default_stop_loss_percentage: "3",
          minimum_trades_for_assessment: minimumTrades,
        },
      });
      setBacktest(result);
      void refreshResearchHistory();
      setFeedback({
        tone: "success",
        message: "اكتمل الاختبار وحُفظت الصفقات ومنحنى الرصيد وافتراضات التنفيذ في المحرك.",
      });
    } catch (error) {
      setFeedback({
        tone: "error",
        message: error instanceof Error ? error.message : "تعذر إجراء الاختبار الخلفي.",
      });
    } finally {
      setBusy(null);
    }
  }

  async function handleApply() {
    if (!backtest || !environment) return;
    const direction = testedDirection(backtest);
    const payload: BacktestStrategyCreateRequest = {
      name: strategyName.trim(),
      environment,
      direction,
    };
    if (!payload.name) {
      setFeedback({ tone: "warning", message: "أدخل اسماً للاستراتيجية قبل إنشائها." });
      return;
    }
    setBusy("apply");
    setFeedback(null);
    try {
      const strategy = await createStrategyFromBacktest(backtest.backtest_id, payload);
      setFeedback({
        tone: "success",
        message: "أنشأ المحرك استراتيجية متوقفة للمراجعة. لم يبدأ أي تداول أو مراقبة تلقائياً.",
      });
      onStrategyCreated(strategy);
    } catch (error) {
      setFeedback({
        tone: "error",
        message: error instanceof Error ? error.message : "تعذر إنشاء الاستراتيجية من النتيجة.",
      });
    } finally {
      setBusy(null);
    }
  }

  if (availableTypes.length === 0) {
    return (
      <div className="strategy-page discovery-page">
        <button className="back-button" type="button" onClick={onBack}>
          <Icon name="chevron" /> العودة
        </button>
        <EmptyState
          title="لا توجد استراتيجيات بحث متاحة"
          description="يجب أن يعلن النوع دعمه للفحص والاختبار الخلفي عبر سجل الاستراتيجيات."
        />
      </div>
    );
  }

  return (
    <div className="strategy-page discovery-page">
      <header className="strategy-page-header discovery-header">
        <div>
          <button className="back-button" type="button" onClick={onBack}>
            <Icon name="chevron" /> العودة إلى العمليات
          </button>
          <span className="eyebrow">بحث غير تنفيذي — Gate.io فقط</span>
          <h1>مختبر اكتشاف الفرص</h1>
          <p>
            افحص العقود وفق شروط الاستراتيجية نفسها، ثم اختبر مرشحاً تاريخياً قبل إنشاء إعداد متوقف للمراجعة.
          </p>
        </div>
        <div className="discovery-safety-note">
          <Icon name="shield" />
          <div>
            <strong>لا يرسل المختبر أوامر</strong>
            <span>الفحص والاختبار منفصلان تماماً عن مدير الأوامر ورصيد الحساب.</span>
          </div>
        </div>
      </header>

      {feedback && (
        <div className={`inline-alert ${feedback.tone}-alert`} role="status">
          <Icon name={feedback.tone === "error" ? "alert" : "activity"} />
          <span>{feedback.message}</span>
        </div>
      )}

      <section className="discovery-stage discovery-scan-stage">
        <div className="discovery-stage-index">1</div>
        <div className="discovery-stage-body">
          <div className="section-heading compact-heading">
            <div>
              <h2>تحديد نموذج الفحص</h2>
              <p>الإعدادات أدناه تأتي من مخطط الاستراتيجية الديناميكي، وليست منطقاً مكرراً في الواجهة.</p>
            </div>
            {metadata && (
              <StatusPill
                label={`${metadata.display_name_ar} · v${metadata.version}`}
                tone={metadata.implementation_status === "working" ? "positive" : "warning"}
              />
            )}
          </div>

          <div className="discovery-control-grid">
            <label className="field">
              <span>نوع الاستراتيجية</span>
              <select value={selectedTypeId} onChange={(event) => setSelectedTypeId(event.target.value)}>
                {availableTypes.map((item) => (
                  <option key={item.type_id} value={item.type_id}>{item.display_name_ar}</option>
                ))}
              </select>
            </label>
            <label className="field">
              <span>الإطار الزمني</span>
              <select value={timeframe} onChange={(event) => setTimeframe(Number(event.target.value))}>
                {(metadata?.supported_timeframes ?? []).map((value) => (
                  <option key={value} value={value}>{timeframeLabel(value)}</option>
                ))}
              </select>
            </label>
            <label className="field">
              <span>أدنى حجم اقتباس 24 ساعة</span>
              <input inputMode="decimal" value={minimumVolume} onChange={(event) => setMinimumVolume(event.target.value)} />
              <small>بالـ USDT؛ يقلل العقود ضعيفة السيولة قبل تحميل الشموع.</small>
            </label>
            <label className="field">
              <span>أقصى عدد عقود للفحص</span>
              <input min={1} max={200} type="number" value={maximumSymbols} onChange={(event) => setMaximumSymbols(Number(event.target.value))} />
            </label>
            <label className="field">
              <span>أقصى عدد مرشحين</span>
              <input min={1} max={200} type="number" value={maximumCandidates} onChange={(event) => setMaximumCandidates(Number(event.target.value))} />
            </label>
            <label className="field">
              <span>أدنى درجة ملاءمة</span>
              <input min={0} max={100} type="number" value={minimumScore} onChange={(event) => setMinimumScore(Number(event.target.value))} />
            </label>
          </div>

          <details className="discovery-configuration" open={Boolean(initialStrategy)}>
            <summary>إعدادات الاستراتيجية المستخدمة في الفحص والاختبار</summary>
            <StrategyConfigurationFields
              metadata={metadata}
              configuration={configuration}
              disabled={busy !== null}
              onChange={(key, value) => setConfiguration((current) => ({ ...current, [key]: value }))}
            />
          </details>

          <div className="discovery-action-row">
            <button className="primary-button" type="button" disabled={busy !== null} onClick={() => void handleScan()}>
              <Icon name={busy === "scan" ? "refresh" : "activity"} />
              {busy === "scan" ? "يفحص Gate.io…" : "فحص السوق بهذه الاستراتيجية"}
            </button>
            <span>
              يحتاج النوع إلى {formatDecimal(metadata?.minimum_backtest_candles)} شمعة مكتملة على الأقل للاختبار الموصى به.
            </span>
          </div>
        </div>
      </section>

      <section className="discovery-stage">
        <div className="discovery-stage-index">2</div>
        <div className="discovery-stage-body">
          <div className="section-heading compact-heading">
            <div>
              <h2>مراجعة المرشحين</h2>
              <p>الدرجة ترتيب تفسيري وفق شروط النوع؛ ليست توقعاً للربح ولا توصية تداول.</p>
            </div>
            {scan && (
              <div className="discovery-scan-summary">
                <span>{scan.result.scanned_symbols} محلل</span>
                <span>{scan.result.universe_symbols} في الكون</span>
                <span>{formatDateTime(scan.result.scanned_at)}</span>
              </div>
            )}
          </div>

          {!scan ? (
            <EmptyState title="لم يبدأ الفحص" description="شغّل الفحص أولاً لعرض العملات المرتبة وأسباب اختيارها." />
          ) : scan.result.candidates.length === 0 ? (
            <EmptyState title="لا توجد مرشحات" description="خفّض درجة الملاءمة أو راجع إعدادات الاستراتيجية والسيولة." />
          ) : (
            <div className="candidate-workspace">
              <div className="candidate-list" role="listbox" aria-label="مرشحو الفحص">
                {scan.result.candidates.map((candidate, index) => (
                  <button
                    className={candidate.symbol === selectedCandidate?.symbol ? "candidate-row active" : "candidate-row"}
                    key={candidate.symbol}
                    type="button"
                    onClick={() => {
                      setSelectedSymbol(candidate.symbol);
                      setBacktest(null);
                      setStrategyName(`${candidate.symbol} — ${metadata?.display_name_ar ?? "استراتيجية"}`);
                    }}
                  >
                    <span className="candidate-rank">{index + 1}</span>
                    <span className="candidate-identity">
                      <strong dir="ltr">{candidate.symbol}</strong>
                      <small>{signalLabel(candidate.signal)} · {candidate.completed_candles} شمعة</small>
                    </span>
                    <span className={`candidate-score score-${scoreTone(candidate.score)}`}>{candidate.score}</span>
                    <span className={`mini-status ${candidate.backtest_ready ? "mini-running" : "mini-paused"}`} />
                  </button>
                ))}
              </div>
              {selectedCandidate && metadata && (
                <CandidateDetail candidate={selectedCandidate} metadata={metadata} />
              )}
            </div>
          )}
          {scan && scan.result.failures.length > 0 && (
            <details className="discovery-failures">
              <summary>عقود تم تخطيها ({scan.result.failures.length})</summary>
              <ul>
                {scan.result.failures.map((failure) => (
                  <li key={failure.symbol}><strong dir="ltr">{failure.symbol}</strong> — {failure.explanation_ar}</li>
                ))}
              </ul>
            </details>
          )}
        </div>
      </section>

      <section className="discovery-stage">
        <div className="discovery-stage-index">3</div>
        <div className="discovery-stage-body">
          <div className="section-heading compact-heading">
            <div>
              <h2>اختبار تاريخي وتقييم</h2>
              <p>ينفذ المحرك الإشارة على الشمعة التالية ويحتسب الرسوم والانزلاق والتمويل التاريخي المتاح.</p>
            </div>
          </div>

          {!selectedCandidate ? (
            <EmptyState title="اختر مرشحاً" description="حدد عملة من نتائج الفحص لإعداد افتراضات الاختبار." />
          ) : (
            <>
              <div className="backtest-assumption-grid">
                <label className="field">
                  <span>الفترة</span>
                  <select value={periodDays} onChange={(event) => setPeriodDays(Number(event.target.value))}>
                    {periodOptions.map((option) => <option key={option.days} value={option.days}>{option.label}</option>)}
                  </select>
                </label>
                <label className="field"><span>الرصيد الابتدائي</span><input inputMode="decimal" value={initialBalance} onChange={(event) => setInitialBalance(event.target.value)} /></label>
                <label className="field"><span>الهامش لكل صفقة</span><input inputMode="decimal" value={marginPerTrade} onChange={(event) => setMarginPerTrade(event.target.value)} /></label>
                <label className="field"><span>الرافعة</span><input min={1} max={200} type="number" value={leverage} onChange={(event) => setLeverage(Number(event.target.value))} /></label>
                <label className="field"><span>رسوم التنفيذ</span><input inputMode="decimal" value={feeRate} onChange={(event) => setFeeRate(event.target.value)} /><small>نسبة عشرية، مثال 0.0005.</small></label>
                <label className="field"><span>الانزلاق بالنقاط الأساسية</span><input min={0} max={1000} type="number" value={slippageBps} onChange={(event) => setSlippageBps(event.target.value)} /></label>
                <label className="field"><span>أدنى صفقات للتقييم</span><input min={1} max={10000} type="number" value={minimumTrades} onChange={(event) => setMinimumTrades(Number(event.target.value))} /></label>
              </div>
              <div className="discovery-action-row">
                <button className="primary-button" type="button" disabled={busy !== null || !selectedCandidate.backtest_ready} onClick={() => void handleBacktest()}>
                  <Icon name={busy === "backtest" ? "refresh" : "chart"} />
                  {busy === "backtest" ? "يجري المحاكاة…" : `اختبار ${selectedCandidate.symbol}`}
                </button>
                {!selectedCandidate.backtest_ready && <span className="warning-text">السجل المكتمل الحالي غير كافٍ.</span>}
              </div>
            </>
          )}

          {backtest && (
            <BacktestReport
              backtest={backtest}
              environment={environment}
              strategyName={strategyName}
              busy={busy === "apply"}
              onNameChange={setStrategyName}
              onApply={() => void handleApply()}
            />
          )}
        </div>
      </section>

      <section className="research-history-section">
        <div className="section-heading compact-heading">
          <div>
            <span className="eyebrow">سجل SQLite</span>
            <h2>أبحاث محفوظة</h2>
            <p>أعد فتح آخر الفحوص والاختبارات بعد إغلاق الواجهة أو إعادة تشغيل المحرك.</p>
          </div>
          <button className="secondary-button" type="button" onClick={() => void refreshResearchHistory()}>
            <Icon name="refresh" /> تحديث
          </button>
        </div>
        <div className="research-history-grid">
          <div className="research-history-column">
            <h3>آخر الفحوص</h3>
            {recentScans.length === 0 ? (
              <span className="muted-text">لا توجد فحوص محفوظة بعد.</span>
            ) : recentScans.map((storedScan) => (
              <button
                className="research-history-row"
                key={storedScan.scan_id}
                type="button"
                onClick={() => {
                  setSelectedTypeId(storedScan.request.strategy_type_id);
                  setTimeframe(storedScan.request.timeframe_minutes);
                  setConfiguration(storedScan.request.configuration);
                  setScan(storedScan);
                  setSelectedSymbol(storedScan.result.candidates[0]?.symbol ?? null);
                  setBacktest(null);
                  setFeedback({ tone: "success", message: "تم تحميل الفحص المحفوظ دون إعادة تنفيذه." });
                }}
              >
                <span>
                  <strong>{strategyTypeLabel(strategyTypes, storedScan.request.strategy_type_id)}</strong>
                  <small>{timeframeLabel(storedScan.request.timeframe_minutes)} · {storedScan.result.candidates.length} مرشح</small>
                </span>
                <time>{formatDateTime(storedScan.created_at)}</time>
              </button>
            ))}
          </div>
          <div className="research-history-column">
            <h3>آخر الاختبارات</h3>
            {recentBacktests.length === 0 ? (
              <span className="muted-text">لا توجد اختبارات محفوظة بعد.</span>
            ) : recentBacktests.map((storedBacktest) => (
              <button
                className="research-history-row"
                key={storedBacktest.backtest_id}
                type="button"
                onClick={() => {
                  const linkedScan = storedBacktest.scan_id
                    ? recentScans.find((item) => item.scan_id === storedBacktest.scan_id) ?? null
                    : null;
                  setSelectedTypeId(storedBacktest.request.strategy_type_id);
                  setTimeframe(storedBacktest.request.timeframe_minutes);
                  setConfiguration(storedBacktest.request.configuration);
                  setScan(linkedScan);
                  setSelectedSymbol(storedBacktest.request.symbol);
                  setBacktest(storedBacktest);
                  setStrategyName(`${storedBacktest.request.symbol} — ${strategyTypeLabel(strategyTypes, storedBacktest.request.strategy_type_id)}`);
                  setFeedback({ tone: "success", message: "تم تحميل الاختبار المحفوظ ونتائجه المدققة." });
                }}
              >
                <span>
                  <strong dir="ltr">{storedBacktest.request.symbol}</strong>
                  <small>{assessmentLabels[storedBacktest.result.assessment.label]} · {formatPercent(storedBacktest.result.metrics.return_percentage)}</small>
                </span>
                <time>{formatDateTime(storedBacktest.created_at)}</time>
              </button>
            ))}
          </div>
        </div>
      </section>
    </div>
  );
}

function CandidateDetail({
  candidate,
  metadata,
}: {
  candidate: StrategyScanCandidate;
  metadata: StrategyTypeMetadata;
}) {
  return (
    <article className="candidate-detail">
      <header>
        <div>
          <span className="eyebrow">المرشح المحدد</span>
          <h3 dir="ltr">{candidate.symbol}</h3>
          <p>{candidate.explanation_ar}</p>
        </div>
        <div className={`candidate-score-large score-${scoreTone(candidate.score)}`}>
          <strong>{candidate.score}</strong>
          <span>من 100</span>
        </div>
      </header>
      <div className="candidate-metric-grid">
        {metadata.candidate_metrics.map((field) => (
          <div key={field.key}>
            <span>{field.label_ar}</span>
            <strong>{displayMetric(candidate.metrics[field.key], field.unit)}</strong>
          </div>
        ))}
      </div>
      <div className="candidate-evidence">
        <div>
          <span>الحالة الآن</span>
          <StatusPill label={candidate.eligible_now ? "مؤهل الآن" : "مرشح للدراسة"} tone={candidate.eligible_now ? "positive" : "neutral"} />
        </div>
        <div>
          <span>جاهزية الاختبار</span>
          <StatusPill label={candidate.backtest_ready ? "سجل كافٍ" : "سجل غير كافٍ"} tone={candidate.backtest_ready ? "positive" : "warning"} />
        </div>
        <div>
          <span>حالة البيانات</span>
          <StatusPill label={candidate.market_data_state} tone={candidate.market_data_state === "fresh" ? "positive" : "warning"} />
        </div>
      </div>
      {candidate.warnings.length > 0 && (
        <ul className="evidence-list warning-list">
          {candidate.warnings.map((warning) => <li key={warning}>{warning}</li>)}
        </ul>
      )}
      {candidate.reason_codes.length > 0 && (
        <details className="reason-code-list">
          <summary>رموز قرار المحرك</summary>
          <code dir="ltr">{candidate.reason_codes.join(" · ")}</code>
        </details>
      )}
    </article>
  );
}

function BacktestReport({
  backtest,
  environment,
  strategyName,
  busy,
  onNameChange,
  onApply,
}: {
  backtest: StoredBacktestRun;
  environment: Environment | null;
  strategyName: string;
  busy: boolean;
  onNameChange: (name: string) => void;
  onApply: () => void;
}) {
  const { metrics, assessment } = backtest.result;
  return (
    <div className="backtest-report">
      <div className={`assessment-banner assessment-${assessment.label}`}>
        <div>
          <span>تقييم قائم على قواعد واضحة</span>
          <h3>{assessmentLabels[assessment.label]}</h3>
          <p>{assessment.summary_ar}</p>
        </div>
        <div className="assessment-score"><strong>{assessment.score}</strong><span>درجة الدليل</span></div>
      </div>

      <div className="backtest-metric-grid">
        <ResultMetric label="صافي النتيجة" value={formatMoney(metrics.net_profit)} tone={Number(metrics.net_profit) >= 0 ? "positive" : "negative"} />
        <ResultMetric label="العائد" value={formatPercent(metrics.return_percentage)} />
        <ResultMetric label="أقصى تراجع" value={formatPercent(metrics.maximum_drawdown_percentage)} tone="warning" />
        <ResultMetric label="عامل الربح" value={formatDecimal(metrics.profit_factor)} />
        <ResultMetric label="الصفقات" value={String(metrics.total_trades)} />
        <ResultMetric label="نسبة الفوز" value={formatPercent(metrics.win_rate_percentage)} />
        <ResultMetric label="الرسوم" value={formatMoney(metrics.fees)} />
        <ResultMetric label="التمويل" value={formatMoney(metrics.funding)} />
        <ResultMetric label="متوسط الربح" value={formatMoney(metrics.average_win)} />
        <ResultMetric label="متوسط الخسارة" value={formatMoney(metrics.average_loss)} />
        <ResultMetric label="أقصى سلسلة خسائر" value={String(metrics.maximum_losing_streak)} />
        <ResultMetric label="عدد الشموع" value={String(backtest.result.candle_count)} />
      </div>

      <EquityCurve points={backtest.result.equity_curve} />

      <div className="backtest-evidence-columns">
        <section>
          <h4>ما يدعم النتيجة</h4>
          {assessment.reasons.length > 0 ? (
            <ul className="evidence-list success-list">{assessment.reasons.map((reason) => <li key={reason}>{reason}</li>)}</ul>
          ) : <span className="muted-text">لا توجد أدلة إيجابية كافية.</span>}
        </section>
        <section>
          <h4>تحذيرات وافتراضات</h4>
          <ul className="evidence-list warning-list">
            {[...assessment.warnings, ...backtest.result.warnings].map((warning) => <li key={warning}>{warning}</li>)}
          </ul>
        </section>
      </div>

      <details className="backtest-trades" open={backtest.result.trades.length <= 8}>
        <summary>الصفقات المحاكاة ({backtest.result.trades.length})</summary>
        <div className="data-table-wrap">
          <table className="data-table">
            <thead><tr><th>#</th><th>الاتجاه</th><th>الدخول</th><th>الخروج</th><th>الصافي</th><th>السبب</th></tr></thead>
            <tbody>
              {backtest.result.trades.map((trade) => (
                <tr key={trade.trade_number}>
                  <td>{trade.trade_number}</td>
                  <td>{signalLabel(trade.direction)}</td>
                  <td>{formatDecimal(trade.entry_price)}</td>
                  <td>{formatDecimal(trade.exit_price)}</td>
                  <td className={Number(trade.net_pnl) >= 0 ? "positive-text" : "negative-text"}>{formatMoney(trade.net_pnl)}</td>
                  <td>{exitReasonLabel(trade.exit_reason)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>

      <section className="backtest-application">
        <div>
          <h4>تحويل النتيجة إلى استراتيجية قابلة للمراجعة</h4>
          <p>ينشئ هذا الإجراء نسخة <strong>متوقفة</strong> فقط. راجعها من صفحتها قبل بدء المراقبة أو التداول.</p>
        </div>
        <label className="field">
          <span>اسم الاستراتيجية</span>
          <input value={strategyName} onChange={(event) => onNameChange(event.target.value)} />
        </label>
        <button className="primary-button" type="button" disabled={busy || !environment || Boolean(backtest.applied_instance_id)} onClick={onApply}>
          <Icon name="plus" />
          {backtest.applied_instance_id ? "تم إنشاء الاستراتيجية" : busy ? "يُنشئ…" : "إنشاء استراتيجية متوقفة"}
        </button>
      </section>
    </div>
  );
}

function ResultMetric({ label, value, tone }: { label: string; value: string; tone?: "positive" | "negative" | "warning" }) {
  return <div className={`backtest-metric ${tone ? `metric-${tone}` : ""}`}><span>{label}</span><strong>{value}</strong></div>;
}

function EquityCurve({ points }: { points: BacktestEquityPoint[] }) {
  if (points.length < 2) return null;
  const values = points.map((point) => Number(point.equity));
  const minimum = Math.min(...values);
  const maximum = Math.max(...values);
  const range = maximum - minimum || 1;
  const coordinates = points.map((point, index) => {
    const x = points.length === 1 ? 0 : (index / (points.length - 1)) * 100;
    const y = 54 - ((Number(point.equity) - minimum) / range) * 48;
    return `${x},${y}`;
  }).join(" ");
  return (
    <figure className="equity-curve">
      <figcaption>
        <div><strong>منحنى الرصيد المحاكى</strong><span>{formatDateTime(points[0].occurred_at)} — {formatDateTime(points.at(-1)?.occurred_at)}</span></div>
        <span>{formatMoney(minimum)} — {formatMoney(maximum)}</span>
      </figcaption>
      <svg aria-label="منحنى الرصيد المحاكى" role="img" viewBox="0 0 100 60" preserveAspectRatio="none">
        <line x1="0" x2="100" y1="54" y2="54" />
        <polyline points={coordinates} />
      </svg>
    </figure>
  );
}

function strategyTypeLabel(
  strategyTypes: StrategyTypeMetadata[],
  typeId: string,
): string {
  return strategyTypes.find((item) => item.type_id === typeId)?.display_name_ar ?? typeId;
}

function testedDirection(backtest: StoredBacktestRun): "long_only" | "short_only" | "both" {
  const direction = backtest.request.configuration.direction;
  return direction === "long_only" || direction === "short_only" || direction === "both"
    ? direction
    : "both";
}

function displayMetric(value: JsonValue | undefined, unit: string | null): string {
  const formatted = typeof value === "number" || typeof value === "string"
    ? formatDecimal(value)
    : value === true
      ? "نعم"
      : value === false
        ? "لا"
        : "غير متاح";
  return unit === "percent" && formatted !== "غير متاح" ? `${formatted}٪` : formatted;
}

function scoreTone(score: number): "good" | "mixed" | "weak" {
  return score >= 70 ? "good" : score >= 45 ? "mixed" : "weak";
}

function signalLabel(signal: string): string {
  return signal === "long" ? "شراء" : signal === "short" ? "بيع" : "محايد";
}

function timeframeLabel(minutes: number): string {
  if (minutes % 10080 === 0) return `${minutes / 10080} أسبوع`;
  if (minutes % 1440 === 0) return `${minutes / 1440} يوم`;
  if (minutes % 60 === 0) return `${minutes / 60} ساعة`;
  return `${minutes} دقيقة`;
}

function exitReasonLabel(reason: string): string {
  const labels: Record<string, string> = {
    take_profit: "جني ربح",
    stop_loss: "وقف خسارة",
    trailing_stop: "وقف متحرك",
    end_of_data: "نهاية البيانات",
  };
  return labels[reason] ?? reason;
}
