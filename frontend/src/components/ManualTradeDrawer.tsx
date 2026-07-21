import { useMemo, useState } from "react";
import type { FormEvent } from "react";

import { previewManualOrder, submitManualOrder } from "../api";
import { formatDecimal, formatMoney, formatPercent } from "../lib/format";
import type {
  Environment,
  EnvironmentRuntimeState,
  ManualOrderPreview,
  ManualOrderRequest,
  ManualOrderResult,
  OrderSizeMode,
  OrderType,
  TimeInForce,
} from "../types";
import { Icon } from "./Icon";
import { StatusPill } from "./StateView";

interface ManualTradeDrawerProps {
  open: boolean;
  environment: Environment;
  environmentRuntime: EnvironmentRuntimeState | null;
  defaultSymbol?: string;
  onClose: () => void;
  onSubmitted: () => void;
}

const percentageOptions = ["10", "25", "50", "75", "100"] as const;

export function ManualTradeDrawer({
  open,
  environment,
  environmentRuntime,
  defaultSymbol = "BTC_USDT",
  onClose,
  onSubmitted,
}: ManualTradeDrawerProps) {
  const [symbol, setSymbol] = useState(defaultSymbol);
  const [direction, setDirection] = useState<"long" | "short">("long");
  const [orderType, setOrderType] = useState<OrderType>("market");
  const [sizeMode, setSizeMode] = useState<OrderSizeMode>("margin");
  const [sizeValue, setSizeValue] = useState("100");
  const [percentage, setPercentage] = useState("25");
  const [leverage, setLeverage] = useState(5);
  const [limitPrice, setLimitPrice] = useState("");
  const [limitExpiresAt, setLimitExpiresAt] = useState(defaultLimitExpiration);
  const [timeInForce, setTimeInForce] = useState<TimeInForce>("ioc");
  const [preview, setPreview] = useState<ManualOrderPreview | null>(null);
  const [result, setResult] = useState<ManualOrderResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const environmentReady = environmentRuntime?.transition_state === "ready"
    && environmentRuntime.activated
    && environmentRuntime.active_engine_environment === environment
    && (
      environment === "paper"
      || environmentRuntime.exchange_adapter_environment === environment
    );
  const environmentBlockMessage = environmentRuntime?.message_ar
    ?? "بيئة التداول غير جاهزة. أكمل التبديل وانتظر تأكيد المحرك قبل المعاينة.";
  const reconciliationFeedback = preview
    ? reconciliationFeedbackFor(preview)
    : null;

  const request = useMemo<ManualOrderRequest>(() => {
    const base: ManualOrderRequest = {
      environment,
      symbol: symbol.trim().toUpperCase(),
      direction,
      order_type: orderType,
      size_mode: sizeMode,
      leverage,
      time_in_force: timeInForce,
    };
    if (sizeMode === "quantity") {
      base.quantity = sizeValue;
    } else if (sizeMode === "margin") {
      base.margin_amount = sizeValue;
    } else {
      base.balance_percentage = percentage;
    }
    if (orderType === "limit") {
      base.limit_price = limitPrice;
      const expiration = Date.parse(limitExpiresAt);
      if (environment === "paper" && Number.isFinite(expiration)) {
        base.expires_at = new Date(expiration).toISOString();
      }
    }
    return base;
  }, [
    direction,
    environment,
    leverage,
    limitExpiresAt,
    limitPrice,
    orderType,
    percentage,
    sizeMode,
    sizeValue,
    symbol,
    timeInForce,
  ]);

  if (!open) {
    return null;
  }

  function invalidatePreview() {
    setPreview(null);
    setResult(null);
    setError(null);
  }

  function changeOrderType(next: OrderType) {
    setOrderType(next);
    setTimeInForce(next === "market" ? "ioc" : "gtc");
    if (next === "limit" && environment === "paper") {
      setLimitExpiresAt(defaultLimitExpiration());
    }
    invalidatePreview();
  }

  async function handlePreview(event: FormEvent) {
    event.preventDefault();
    if (!environmentReady) {
      setPreview(null);
      setError(environmentBlockMessage);
      return;
    }
    setBusy(true);
    setError(null);
    setResult(null);
    try {
      setPreview(await previewManualOrder(request));
    } catch (caught) {
      setPreview(null);
      setError(caught instanceof Error ? caught.message : "تعذر إنشاء معاينة الأمر.");
    } finally {
      setBusy(false);
    }
  }

  async function handleSubmit() {
    if (!environmentReady) {
      setError(environmentBlockMessage);
      return;
    }
    if (!preview || !preview.can_submit) {
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const submitted = await submitManualOrder(preview);
      setResult(submitted);
      if (submitted.accepted) {
        onSubmitted();
      }
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "تعذر إرسال الأمر.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="drawer-backdrop" role="presentation" onMouseDown={onClose}>
      <aside
        aria-label="التداول اليدوي للعقود الدائمة"
        aria-modal="true"
        className="trade-drawer"
        role="dialog"
        onMouseDown={(event) => event.stopPropagation()}
      >
        <header className="drawer-header">
          <div>
            <span className="eyebrow">مدير الأوامر المركزي</span>
            <h2>أمر عقود دائمة يدوي</h2>
            <p>المعاينة والتنفيذ يمران عبر محرك RangeBot ومحددات المخاطر.</p>
          </div>
          <button className="icon-button" type="button" onClick={onClose} aria-label="إغلاق">
            <Icon name="x" />
          </button>
        </header>

        <div className={`live-funds-warning environment-banner ${environment}`} role="status">
          <Icon name={environment === "live" ? "alert" : "shield"} />
          <div>
            <strong>
              {environment === "live"
                ? "LIVE — REAL FUNDS"
                : environment === "testnet"
                  ? "TESTNET"
                  : "PAPER"}
            </strong>
            <span>
              {environment === "live"
                ? "أي Order مقبول سيستخدم رصيد Gate.io الحقيقي."
                : environment === "testnet"
                  ? "كل Orders تُرسل إلى Gate.io Futures Testnet فقط."
                  : "كل Orders محاكاة محلية ولا تستخدم أموالاً حقيقية."}
            </span>
          </div>
        </div>

        {!environmentReady && (
          <div className="inline-alert error-alert environment-blocker" role="alert">
            <Icon name="alert" />
            <span>{environmentBlockMessage}</span>
          </div>
        )}

        <form className="trade-form" onSubmit={handlePreview}>
          <div className="segmented-control" aria-label="نوع الأمر">
            <button
              className={orderType === "market" ? "active" : ""}
              type="button"
              onClick={() => changeOrderType("market")}
            >
              Market
            </button>
            <button
              className={orderType === "limit" ? "active" : ""}
              type="button"
              onClick={() => changeOrderType("limit")}
            >
              Limit
            </button>
          </div>

          <div className="segmented-control direction-control" aria-label="اتجاه الأمر">
            <button
              className={direction === "long" ? "active long" : ""}
              type="button"
              onClick={() => {
                setDirection("long");
                invalidatePreview();
              }}
            >
              شراء / Long
            </button>
            <button
              className={direction === "short" ? "active short" : ""}
              type="button"
              onClick={() => {
                setDirection("short");
                invalidatePreview();
              }}
            >
              بيع / Short
            </button>
          </div>

          <label className="field">
            <span>عقد Gate.io USDT الدائم</span>
            <input
              autoComplete="off"
              value={symbol}
              onChange={(event) => {
                setSymbol(event.target.value);
                invalidatePreview();
              }}
              placeholder="BTC_USDT"
            />
          </label>

          <div className="field-group three-columns">
            <label className="field">
              <span>طريقة الحجم</span>
              <select
                value={sizeMode}
                onChange={(event) => {
                  setSizeMode(event.target.value as OrderSizeMode);
                  invalidatePreview();
                }}
              >
                <option value="margin">هامش USDT</option>
                <option value="quantity">كمية العقود</option>
                <option value="balance_percentage">نسبة من الرصيد</option>
              </select>
            </label>
            <label className="field">
              <span>الرافعة</span>
              <input
                min="1"
                step="1"
                type="number"
                value={leverage}
                onChange={(event) => {
                  setLeverage(Number(event.target.value));
                  invalidatePreview();
                }}
              />
            </label>
            <label className="field">
              <span>مدة الأمر</span>
              <select
                value={timeInForce}
                onChange={(event) => {
                  setTimeInForce(event.target.value as TimeInForce);
                  invalidatePreview();
                }}
              >
                {orderType === "market" ? (
                  <>
                    <option value="ioc">IOC</option>
                    <option value="fok">FOK</option>
                  </>
                ) : (
                  <>
                    <option value="gtc">GTC</option>
                    <option value="ioc">IOC</option>
                    <option value="poc">POC</option>
                    <option value="fok">FOK</option>
                  </>
                )}
              </select>
            </label>
          </div>

          {sizeMode === "balance_percentage" ? (
            <div className="field">
              <span>النسبة من الرصيد المتاح</span>
              <div className="percentage-grid">
                {percentageOptions.map((option) => (
                  <button
                    className={percentage === option ? "active" : ""}
                    key={option}
                    type="button"
                    onClick={() => {
                      setPercentage(option);
                      invalidatePreview();
                    }}
                  >
                    {option}٪
                  </button>
                ))}
              </div>
            </div>
          ) : (
            <label className="field">
              <span>{sizeMode === "margin" ? "الهامش" : "كمية العقود"}</span>
              <input
                inputMode="decimal"
                value={sizeValue}
                onChange={(event) => {
                  setSizeValue(event.target.value);
                  invalidatePreview();
                }}
                placeholder="0"
              />
            </label>
          )}

          {orderType === "limit" && (
            <div className={environment === "paper" ? "field-group two-columns" : "field-group"}>
              <label className="field">
                <span>سعر Limit</span>
                <input
                  inputMode="decimal"
                  value={limitPrice}
                  onChange={(event) => {
                    setLimitPrice(event.target.value);
                    invalidatePreview();
                  }}
                  placeholder="0"
                />
              </label>
              {environment === "paper" && (
                <label className="field">
                  <span>انتهاء الأمر المحلي</span>
                  <input
                    required
                    type="datetime-local"
                    value={limitExpiresAt}
                    onChange={(event) => {
                      setLimitExpiresAt(event.target.value);
                      invalidatePreview();
                    }}
                  />
                  <small>يُلغى أمر Paper المعلق تلقائياً بعد هذا الوقت.</small>
                </label>
              )}
            </div>
          )}

          <button className="primary-button preview-button" type="submit" disabled={busy || !environmentReady}>
            <Icon name="shield" />
            {busy ? "جارٍ التحقق…" : "معاينة وفحص الأمر"}
          </button>
        </form>

        {error && <div className="inline-alert error-alert" role="alert">{error}</div>}

        {preview && (
          <section className="order-preview" aria-label="معاينة الأمر">
            <div className="section-title-row">
              <div>
                <span className="eyebrow">بيانات المحرك</span>
                <h3>المعاينة قبل الإرسال</h3>
              </div>
              <StatusPill
                label={preview.can_submit ? "جاهز للإرسال" : "محظور"}
                tone={preview.can_submit ? "positive" : "negative"}
              />
            </div>

            {reconciliationFeedback && (
              <div className="inline-alert warning-alert" role="status">
                <strong>{reconciliationFeedback.title}</strong>
                <span>{reconciliationFeedback.message}</span>
              </div>
            )}

            <div className="preview-price-strip">
              <Metric label="Last" value={formatDecimal(preview.last_price)} />
              <Metric label="Mark" value={formatDecimal(preview.mark_price)} />
              <Metric label="Best bid" value={formatDecimal(preview.best_bid)} />
              <Metric label="Best ask" value={formatDecimal(preview.best_ask)} />
            </div>

            <div className="preview-metrics">
              <Metric label="الكمية المقدرة" value={formatDecimal(preview.estimated_quantity)} />
              <Metric label="Minimum Quantity" value={formatDecimal(preview.minimum_quantity)} />
              <Metric label="القيمة الاسمية" value={formatMoney(preview.estimated_notional)} />
              <Metric label="Approx. Minimum Margin" value={formatMoney(preview.approximate_minimum_margin)} />
              <Metric label="الهامش المقدر" value={formatMoney(preview.estimated_margin)} />
              <Metric label="رسوم الفتح" value={formatMoney(preview.estimated_opening_fee)} />
              <Metric label="Take Profit" value={formatDecimal(preview.estimated_take_profit_price)} />
              <Metric label="Stop Loss" value={formatDecimal(preview.estimated_stop_loss_price)} />
              <Metric label="سعر التصفية المقدر" value={formatDecimal(preview.estimated_liquidation_price)} />
              <Metric label="سلوك السيولة" value={preview.estimated_liquidity_behavior.toUpperCase()} />
              <Metric label="مسافة Limit" value={formatPercent(preview.limit_distance_percentage)} />
              <Metric label="الرصيد المتاح" value={formatMoney(preview.available_balance)} />
            </div>

            {preview.validation_issues.length > 0 && (
              <div className="validation-list" role="alert">
                <strong>يجب معالجة التالي قبل الإرسال:</strong>
                <ul>
                  {preview.validation_issues.map((issue) => (
                    <li key={`${issue.code}-${issue.field ?? "general"}`}>{issue.message_ar}</li>
                  ))}
                </ul>
              </div>
            )}

            <button
              className={preview.uses_real_funds ? "danger-button submit-order" : "primary-button submit-order"}
              type="button"
              disabled={busy || !environmentReady || !preview.can_submit}
              onClick={handleSubmit}
            >
              <Icon name="trade" />
              {busy
                ? "جارٍ الإرسال…"
                : preview.uses_real_funds
                  ? "إرسال أمر LIVE بأموال حقيقية"
                  : "إرسال الأمر عبر المحرك"}
            </button>
          </section>
        )}

        {result && (
          <div className={result.accepted ? "inline-alert success-alert" : "inline-alert error-alert"}>
            <strong>{result.accepted ? "تم قبول الأمر" : "تم رفض الأمر"}</strong>
            <span>{result.message_ar}</span>
            {result.order_id && <code>{result.order_id}</code>}
          </div>
        )}
      </aside>
    </div>
  );
}

function reconciliationFeedbackFor(preview: ManualOrderPreview): {
  title: string;
  message: string;
} | null {
  const codes = new Set(preview.validation_issues.map((issue) => issue.code));
  if (codes.has("reconciliation_refreshing")) {
    return {
      title: "Account sync is running",
      message: "عادت Preview فوراً من دون انتظار Gate.io. يبقى Submit محظوراً حتى تكتمل المزامنة.",
    };
  }
  if (codes.has("reconciliation_snapshot_stale")) {
    return {
      title: "Account snapshot is stale",
      message: "يتم طلب لقطة أحدث في الخلفية قبل السماح بأي Order.",
    };
  }
  if (codes.has("reconciliation_snapshot_missing")) {
    return {
      title: "Account snapshot is not available yet",
      message: "انتظر اكتمال أول Reconciliation ثم أعد Preview.",
    };
  }
  if (
    codes.has("reconciliation_failed")
    || codes.has("reconciliation_timeout")
  ) {
    return {
      title: "Account sync failed",
      message: "راجع Credentials والاتصال ثم أعد Reconciliation. لم يُرسل أي Order.",
    };
  }
  return null;
}

function defaultLimitExpiration(): string {
  const expiration = new Date(Date.now() + 60 * 60 * 1000);
  const localOffset = expiration.getTimezoneOffset() * 60 * 1000;
  return new Date(expiration.getTime() - localOffset).toISOString().slice(0, 16);
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="metric-pair">
      <span>{label}</span>
      <strong dir="ltr">{value}</strong>
    </div>
  );
}
