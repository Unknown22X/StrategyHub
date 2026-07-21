import { useEffect, useMemo, useState } from "react";

import {
  loadTradeHistory,
  loadTradeHistorySummary,
  type TradeHistoryFilters,
} from "../api";
import {
  formatDateTime,
  formatDecimal as formatDecimalOriginal,
  formatMoney,
} from "../lib/format";

const formatDecimal = (
  value: string | number | null | undefined,
  _precision?: number,
) => formatDecimalOriginal(value);
import type {
  Environment,
  RemoteData,
  StrategyInstance,
  TradeFill,
  TradeHistorySummary,
} from "../types";
import { Icon } from "./Icon";
import { EmptyState, StateView, StatusPill } from "./StateView";

interface TradeHistoryPageProps {
  currentEnvironment: Environment | null;
  strategies: StrategyInstance[];
  onBack: () => void;
}

type Period = "today" | "7d" | "30d" | "all";

const periodLabels: Record<Period, string> = {
  today: "اليوم",
  "7d": "7 أيام",
  "30d": "30 يوماً",
  all: "الكل",
};

function periodStart(period: Period): string | undefined {
  if (period === "all") return undefined;
  const now = new Date();
  if (period === "today") {
    const riyadh = new Date(now.toLocaleString("en-US", { timeZone: "Asia/Riyadh" }));
    riyadh.setHours(0, 0, 0, 0);
    return new Date(riyadh.getTime() - 3 * 60 * 60 * 1000).toISOString();
  }
  const days = period === "7d" ? 7 : 30;
  return new Date(now.getTime() - days * 24 * 60 * 60 * 1000).toISOString();
}

function sideLabel(fill: TradeFill): string {
  if (fill.position_effect === "close") {
    return fill.side === "sell" ? "إغلاق Long" : "إغلاق Short";
  }
  if (fill.position_effect === "mixed") return "تنفيذ مختلط";
  return fill.side === "buy" ? "فتح Long" : "فتح Short";
}

function originLabel(fill: TradeFill): string {
  if (fill.strategy_name_snapshot) return fill.strategy_name_snapshot;
  switch (fill.origin) {
    case "manual": return "تداول يدوي";
    case "automatic_strategy": return "استراتيجية تلقائية";
    case "monitoring_conversion": return "تحويل من المراقبة";
    case "legacy_automatic": return "تشغيل تلقائي قديم";
    case "external": return "خارجي / غير مُدار";
    default: return "غير منسوب";
  }
}

export function TradeHistoryPage({
  currentEnvironment,
  strategies,
  onBack,
}: TradeHistoryPageProps) {
  const [environment, setEnvironment] = useState<Environment | "all">(
    currentEnvironment ?? "all",
  );
  const [strategyId, setStrategyId] = useState("");
  const [contract, setContract] = useState("");
  const [period, setPeriod] = useState<Period>("30d");
  const [fills, setFills] = useState<RemoteData<TradeFill[]>>({ status: "loading" });
  const [summary, setSummary] = useState<RemoteData<TradeHistorySummary>>({ status: "loading" });

  const symbols = useMemo(
    () => [...new Set(strategies.map((strategy) => strategy.symbol))].sort(),
    [strategies],
  );

  useEffect(() => {
    const controller = new AbortController();
    const filters: TradeHistoryFilters = {
      environment: environment === "all" ? undefined : environment,
      instanceId: strategyId || undefined,
      contract: contract || undefined,
      since: periodStart(period),
      limit: 1000,
    };
    setFills({ status: "loading" });
    setSummary({ status: "loading" });
    Promise.all([
      loadTradeHistory(filters, controller.signal),
      loadTradeHistorySummary(filters, controller.signal),
    ])
      .then(([historyRows, summaryRow]) => {
        setFills({ status: "ready", data: historyRows });
        setSummary({ status: "ready", data: summaryRow });
      })
      .catch((error) => {
        if (error instanceof DOMException && error.name === "AbortError") return;
        const message = error instanceof Error ? error.message : "تعذر تحميل سجل الصفقات.";
        setFills({ status: "error", message });
        setSummary({ status: "error", message });
      });
    return () => controller.abort();
  }, [contract, environment, period, strategyId]);

  return (
    <section className="trade-history-page page-surface" aria-labelledby="trade-history-title">
      <header className="page-heading compact-heading">
        <div>
          <button className="text-button back-button" type="button" onClick={onBack}>
            <Icon name="chevron" size={16} />
            العودة إلى لوحة العمليات
          </button>
          <span className="eyebrow">التنفيذ الفعلي والمُحاكى من المحرك</span>
          <h1 id="trade-history-title">سجل الصفقات المنفذة</h1>
          <p>
            بيانات تنفيذ غير قابلة لإعادة الكتابة، مصدرها Gate.io في Live/Testnet ومحرك Paper المحلي.
          </p>
        </div>
        <div className="heading-status-cluster">
          <StatusPill tone="neutral">{environment === "all" ? "كل البيئات" : environment.toUpperCase()}</StatusPill>
          <StatusPill tone="positive">ملكية الاستراتيجية محفوظة وقت التنفيذ</StatusPill>
        </div>
      </header>

      <div className="trade-history-filters" aria-label="مرشحات سجل الصفقات">
        <label>
          <span>البيئة</span>
          <select value={environment} onChange={(event) => setEnvironment(event.target.value as Environment | "all")}>
            <option value="all">كل البيئات</option>
            <option value="live">Live</option>
            <option value="testnet">Testnet</option>
            <option value="paper">Paper</option>
          </select>
        </label>
        <label>
          <span>الاستراتيجية</span>
          <select value={strategyId} onChange={(event) => setStrategyId(event.target.value)}>
            <option value="">كل الاستراتيجيات</option>
            {strategies.map((strategy) => (
              <option key={strategy.instance_id} value={strategy.instance_id}>{strategy.name}</option>
            ))}
          </select>
        </label>
        <label>
          <span>العقد</span>
          <select value={contract} onChange={(event) => setContract(event.target.value)}>
            <option value="">كل العقود</option>
            {symbols.map((symbol) => <option key={symbol} value={symbol}>{symbol}</option>)}
          </select>
        </label>
        <div className="segmented-control trade-period-control" role="group" aria-label="الفترة">
          {(Object.keys(periodLabels) as Period[]).map((value) => (
            <button
              className={period === value ? "active" : ""}
              key={value}
              type="button"
              onClick={() => setPeriod(value)}
            >
              {periodLabels[value]}
            </button>
          ))}
        </div>
      </div>

      <StateView state={summary} loadingLabel="جارٍ حساب ملخص التنفيذ...">
        {(data) => (
          <div className="summary-grid trade-history-summary">
            <article className="summary-card"><span>التنفيذات</span><strong>{data.fills}</strong></article>
            <article className="summary-card"><span>الكمية المفتوحة</span><strong>{formatDecimal(data.opened_quantity)}</strong></article>
            <article className="summary-card"><span>الكمية المغلقة</span><strong>{formatDecimal(data.closed_quantity)}</strong></article>
            <article className="summary-card">
              <span>صافي النتيجة المحققة</span>
              <strong>{data.realized_pnl === null ? "غير متاح" : formatMoney(data.realized_pnl)}</strong>
              <small>{data.realized_pnl_known_fills} من {data.fills} تنفيذات تحمل نتيجة محققة</small>
            </article>
            <article className="summary-card"><span>الرسوم / الحسومات</span><strong>{formatMoney(data.fees)}</strong></article>
            <article className="summary-card"><span>قيمة التداول الإجمالية</span><strong>{formatMoney(data.gross_trade_value)}</strong></article>
          </div>
        )}
      </StateView>

      <StateView state={fills} loadingLabel="جارٍ تحميل سجل الصفقات...">
        {(rows) => rows.length === 0 ? (
          <EmptyState
            title="لا توجد تنفيذات مطابقة"
            description="غيّر البيئة أو الفترة أو الاستراتيجية. لن تعرض الواجهة بيانات نموذجية بديلة."
            icon="trade"
          />
        ) : (
          <div className="table-scroll trade-history-table-wrap">
            <table className="data-table trade-history-table">
              <thead>
                <tr>
                  <th>الوقت</th>
                  <th>العقد</th>
                  <th>التنفيذ</th>
                  <th>السعر</th>
                  <th>الكمية</th>
                  <th>الرسوم</th>
                  <th>المحقق</th>
                  <th>المالك</th>
                  <th>المصدر</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((fill) => (
                  <tr key={`${fill.environment}-${fill.external_trade_id}`}>
                    <td>{formatDateTime(fill.occurred_at)}</td>
                    <td><strong>{fill.contract}</strong><small>{fill.environment.toUpperCase()}</small></td>
                    <td><StatusPill tone={fill.position_effect === "close" ? "warning" : "positive"}>{sideLabel(fill)}</StatusPill></td>
                    <td>{formatDecimal(fill.price)}</td>
                    <td>{formatDecimal(fill.quantity)}</td>
                    <td className={Number(fill.fee) < 0 ? "positive-number" : "negative-number"}>{formatMoney(fill.fee)}</td>
                    <td className={fill.realized_pnl === null ? "" : Number(fill.realized_pnl) >= 0 ? "positive-number" : "negative-number"}>
                      {fill.realized_pnl === null ? "غير متاح من سجل التنفيذ" : formatMoney(fill.realized_pnl)}
                    </td>
                    <td><strong>{originLabel(fill)}</strong>{fill.run_id && <small>Run {fill.run_id.slice(0, 8)}</small>}</td>
                    <td>{fill.source === "gate_rest" ? "Gate.io REST" : "Paper Engine"}<small>{fill.role}</small></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </StateView>
    </section>
  );
}
