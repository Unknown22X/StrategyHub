import { useEffect, useMemo, useState } from "react";

import { loadMarketCandles, loadMarketSnapshot } from "../api";
import { formatDateTime, formatDecimal } from "../lib/format";
import type {
  JsonValue,
  MarketCandle,
  MarketCandleSeries,
  MarketDataSnapshot,
  RemoteData,
  StrategyDecision,
  StrategyInstance,
  StrategyTypeMetadata,
} from "../types";
import { Icon } from "./Icon";
import { EmptyState, StatusPill } from "./StateView";

interface StrategyChartProps {
  strategy: StrategyInstance;
  metadata: StrategyTypeMetadata | null;
  decision: StrategyDecision | null;
}

type PriceReference = "last" | "mark";

interface OverlayLine {
  key: string;
  label: string;
  price: number;
}

export function StrategyChart({ strategy, metadata, decision }: StrategyChartProps) {
  const [timeframe, setTimeframe] = useState(strategy.timeframe_minutes);
  const [visibleCount, setVisibleCount] = useState<30 | 60 | 100>(60);
  const [priceReference, setPriceReference] = useState<PriceReference>("last");
  const [showOverlays, setShowOverlays] = useState(true);
  const [fullscreen, setFullscreen] = useState(false);
  const [series, setSeries] = useState<RemoteData<MarketCandleSeries>>({ status: "loading" });
  const [snapshot, setSnapshot] = useState<RemoteData<MarketDataSnapshot>>({ status: "loading" });

  useEffect(() => {
    setTimeframe(strategy.timeframe_minutes);
  }, [strategy.instance_id, strategy.timeframe_minutes]);

  useEffect(() => {
    let cancelled = false;
    const controller = new AbortController();

    async function refreshChart() {
      try {
        const [candles, market] = await Promise.all([
          loadMarketCandles(strategy.symbol, timeframe, controller.signal),
          loadMarketSnapshot(strategy.symbol, controller.signal),
        ]);
        if (!cancelled) {
          setSeries({ status: "ready", data: candles });
          setSnapshot({ status: "ready", data: market });
        }
      } catch (error) {
        if (cancelled || (error instanceof DOMException && error.name === "AbortError")) {
          return;
        }
        const message = error instanceof Error ? error.message : "تعذر تحميل بيانات الرسم.";
        setSeries({ status: "error", message });
        setSnapshot({ status: "error", message });
      }
    }

    setSeries({ status: "loading" });
    setSnapshot({ status: "loading" });
    void refreshChart();
    const interval = window.setInterval(() => void refreshChart(), 15_000);
    return () => {
      cancelled = true;
      controller.abort();
      window.clearInterval(interval);
    };
  }, [strategy.symbol, timeframe]);

  const chart = useMemo(() => {
    if (series.status !== "ready") return null;
    const candles = series.data.candles.slice(-visibleCount);
    const overlays = showOverlays
      ? buildOverlayLines(metadata, decision)
      : [];
    const market = snapshot.status === "ready" ? snapshot.data : null;
    const referenceValue = market
      ? Number(priceReference === "mark" ? market.mark_price ?? market.last_price : market.last_price)
      : null;
    return buildChartGeometry(candles, overlays, referenceValue);
  }, [decision, metadata, priceReference, series, showOverlays, snapshot, visibleCount]);

  const timeframeOptions = metadata?.supported_timeframes.length
    ? metadata.supported_timeframes
    : [strategy.timeframe_minutes];
  const market = snapshot.status === "ready" ? snapshot.data : null;

  return (
    <section className={fullscreen ? "strategy-chart-panel fullscreen-chart" : "strategy-chart-panel"}>
      <header className="strategy-chart-header">
        <div>
          <span className="eyebrow">Gate.io · بيانات المحرك الطبيعية</span>
          <h3>{strategy.symbol} · {timeframe}m</h3>
        </div>
        <div className="strategy-chart-controls">
          <label>
            <span>الإطار</span>
            <select value={timeframe} onChange={(event) => setTimeframe(Number(event.target.value))}>
              {timeframeOptions.map((item) => <option key={item} value={item}>{item}m</option>)}
            </select>
          </label>
          <label>
            <span>التكبير</span>
            <select value={visibleCount} onChange={(event) => setVisibleCount(Number(event.target.value) as 30 | 60 | 100)}>
              <option value={30}>30 شمعة</option>
              <option value={60}>60 شمعة</option>
              <option value={100}>100 شمعة</option>
            </select>
          </label>
          <div className="mode-segment compact-segment">
            <button className={priceReference === "last" ? "active" : ""} type="button" onClick={() => setPriceReference("last")}>Last</button>
            <button className={priceReference === "mark" ? "active" : ""} type="button" onClick={() => setPriceReference("mark")}>Mark</button>
          </div>
          <button className={showOverlays ? "secondary-button active-control" : "secondary-button"} type="button" onClick={() => setShowOverlays((value) => !value)}>
            <Icon name="chart" />
            الطبقات
          </button>
          <button className="icon-button" type="button" onClick={() => setFullscreen((value) => !value)} aria-label={fullscreen ? "إغلاق ملء الشاشة" : "عرض بملء الشاشة"}>
            <Icon name={fullscreen ? "x" : "grid"} />
          </button>
        </div>
      </header>

      <div className="strategy-chart-status">
        <span>{market ? `${priceReference === "mark" ? "Mark" : "Last"}: ${formatDecimal(priceReference === "mark" ? market.mark_price ?? market.last_price : market.last_price)}` : "السعر غير متاح"}</span>
        <StatusPill label={marketStateLabel(market?.state)} tone={marketStateTone(market?.state)} />
        <span>{series.status === "ready" ? `آخر تحديث: ${formatDateTime(series.data.updated_at)}` : ""}</span>
      </div>

      {series.status === "loading" ? (
        <div className="chart-state"><span className="loading-ring" /> جارٍ تحميل الشموع…</div>
      ) : series.status === "error" ? (
        <EmptyState title="الرسم غير متاح" description={series.message} />
      ) : !chart || chart.candles.length === 0 ? (
        <EmptyState title="لا توجد شموع كافية" description="سيظهر الرسم بعد أن يجمع Market Data Manager شموع هذا العقد والإطار." />
      ) : (
        <svg className="candlestick-chart" viewBox="0 0 1000 390" role="img" aria-label={`رسم شموع ${strategy.symbol}`}>
          <rect className="chart-background" x="0" y="0" width="1000" height="390" rx="10" />
          {chart.grid.map((line) => (
            <g key={line.value}>
              <line className="chart-grid-line" x1="58" x2="982" y1={line.y} y2={line.y} />
              <text className="chart-axis-label" x="52" y={line.y + 4} textAnchor="end">{formatAxis(line.value)}</text>
            </g>
          ))}
          {chart.candles.map((candle) => (
            <g className={candle.up ? "candle up" : "candle down"} key={candle.key} opacity={candle.closed ? 1 : 0.55}>
              <line x1={candle.x} x2={candle.x} y1={candle.highY} y2={candle.lowY} />
              <rect x={candle.x - candle.width / 2} y={candle.bodyY} width={candle.width} height={candle.bodyHeight} rx="1" />
            </g>
          ))}
          {chart.overlays.map((overlay) => (
            <g key={overlay.key}>
              <line className="chart-overlay-line" x1="58" x2="982" y1={overlay.y} y2={overlay.y} />
              <text className="chart-overlay-label" x="975" y={overlay.y - 5} textAnchor="end">{overlay.label} · {formatAxis(overlay.price)}</text>
            </g>
          ))}
          {chart.reference && (
            <g>
              <line className="chart-reference-line" x1="58" x2="982" y1={chart.reference.y} y2={chart.reference.y} />
              <text className="chart-reference-label" x="975" y={chart.reference.y - 5} textAnchor="end">{priceReference.toUpperCase()} · {formatAxis(chart.reference.price)}</text>
            </g>
          )}
          <text className="chart-time-label" x="58" y="378">{formatShortTime(chart.firstOpenedAt)}</text>
          <text className="chart-time-label" x="982" y="378" textAnchor="end">{formatShortTime(chart.lastClosedAt)}</text>
        </svg>
      )}
    </section>
  );
}

function buildOverlayLines(
  metadata: StrategyTypeMetadata | null,
  decision: StrategyDecision | null,
): OverlayLine[] {
  if (!metadata || !decision) return [];
  const labels = new Map(metadata.live_analysis_fields.map((field) => [field.key, field.label_ar]));
  return metadata.chart_overlays.flatMap((key) => {
    const value = numericJsonValue(decision.analysis[key]);
    return value === null ? [] : [{ key, label: labels.get(key) ?? overlayLabel(key), price: value }];
  });
}

function numericJsonValue(value: JsonValue | undefined): number | null {
  if (typeof value === "number") return Number.isFinite(value) ? value : null;
  if (typeof value === "string" && value.trim()) {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : null;
  }
  return null;
}

function overlayLabel(key: string): string {
  return key.replaceAll("_", " ");
}

function buildChartGeometry(candles: MarketCandle[], overlays: OverlayLine[], referencePrice: number | null) {
  const parsed = candles.flatMap((candle) => {
    const open = Number(candle.open);
    const high = Number(candle.high);
    const low = Number(candle.low);
    const close = Number(candle.close);
    return [open, high, low, close].every(Number.isFinite)
      ? [{ source: candle, open, high, low, close }]
      : [];
  });
  if (parsed.length === 0) return null;
  const values = parsed.flatMap((item) => [item.high, item.low]);
  values.push(...overlays.map((item) => item.price));
  if (referencePrice !== null && Number.isFinite(referencePrice)) values.push(referencePrice);
  let minimum = Math.min(...values);
  let maximum = Math.max(...values);
  if (minimum === maximum) {
    minimum *= 0.995;
    maximum *= 1.005;
  }
  const padding = Math.max((maximum - minimum) * 0.08, maximum * 0.0005);
  minimum -= padding;
  maximum += padding;
  const top = 18;
  const bottom = 350;
  const left = 58;
  const right = 982;
  const plotHeight = bottom - top;
  const step = (right - left) / parsed.length;
  const y = (price: number) => top + ((maximum - price) / (maximum - minimum)) * plotHeight;
  const grid = Array.from({ length: 5 }, (_, index) => {
    const value = maximum - ((maximum - minimum) * index) / 4;
    return { value, y: y(value) };
  });
  return {
    candles: parsed.map((item, index) => {
      const openY = y(item.open);
      const closeY = y(item.close);
      return {
        key: item.source.opened_at,
        x: left + step * (index + 0.5),
        highY: y(item.high),
        lowY: y(item.low),
        bodyY: Math.min(openY, closeY),
        bodyHeight: Math.max(1.5, Math.abs(closeY - openY)),
        width: Math.max(2, Math.min(10, step * 0.56)),
        up: item.close >= item.open,
        closed: item.source.closed,
      };
    }),
    overlays: overlays.map((item) => ({ ...item, y: y(item.price) })),
    reference: referencePrice !== null && Number.isFinite(referencePrice)
      ? { price: referencePrice, y: y(referencePrice) }
      : null,
    grid,
    firstOpenedAt: parsed[0].source.opened_at,
    lastClosedAt: parsed[parsed.length - 1].source.closed_at,
  };
}

function marketStateLabel(state: MarketDataSnapshot["state"] | undefined): string {
  if (state === "fresh") return "بيانات حديثة";
  if (state === "stale") return "بيانات قديمة";
  if (state === "reconnecting") return "إعادة اتصال";
  return "غير متاح";
}

function marketStateTone(state: MarketDataSnapshot["state"] | undefined): "positive" | "warning" | "negative" | "neutral" {
  if (state === "fresh") return "positive";
  if (state === "stale" || state === "reconnecting") return "warning";
  if (state === "unavailable") return "negative";
  return "neutral";
}

function formatAxis(value: number): string {
  if (Math.abs(value) >= 1000) return value.toLocaleString("en-US", { maximumFractionDigits: 2 });
  if (Math.abs(value) >= 1) return value.toLocaleString("en-US", { maximumFractionDigits: 4 });
  return value.toLocaleString("en-US", { maximumSignificantDigits: 6 });
}

function formatShortTime(value: string): string {
  return new Intl.DateTimeFormat("ar-SA", {
    timeZone: "Asia/Riyadh",
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(value));
}
