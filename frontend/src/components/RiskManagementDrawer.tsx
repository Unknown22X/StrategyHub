import { useEffect, useState } from "react";

import { loadAccountRiskPolicy, saveAccountRiskPolicy } from "../api";
import type { AccountRiskPolicy, Environment } from "../types";
import { Icon } from "./Icon";

interface RiskManagementDrawerProps {
  open: boolean;
  environment: Environment | null;
  onClose: () => void;
  onSaved: () => void;
}

type Feedback = { tone: "success" | "warning" | "error"; message: string } | null;

export function RiskManagementDrawer({
  open,
  environment,
  onClose,
  onSaved,
}: RiskManagementDrawerProps) {
  const [policy, setPolicy] = useState<AccountRiskPolicy | null>(null);
  const [dailyLossEnabled, setDailyLossEnabled] = useState(true);
  const [dailyLossLimit, setDailyLossLimit] = useState("100");
  const [losingTradeEnabled, setLosingTradeEnabled] = useState(true);
  const [losingTradeLimit, setLosingTradeLimit] = useState("3");
  const [automaticTradeEnabled, setAutomaticTradeEnabled] = useState(true);
  const [automaticTradeLimit, setAutomaticTradeLimit] = useState("5");
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [feedback, setFeedback] = useState<Feedback>(null);

  useEffect(() => {
    if (!open) return;
    const controller = new AbortController();
    setLoading(true);
    setFeedback(null);
    loadAccountRiskPolicy(controller.signal)
      .then((loaded) => {
        setPolicy(loaded);
        setDailyLossEnabled(loaded.daily_loss_enabled);
        setDailyLossLimit(loaded.daily_loss_limit);
        setLosingTradeEnabled(loaded.losing_trade_enabled);
        setLosingTradeLimit(String(loaded.losing_trade_limit));
        setAutomaticTradeEnabled(loaded.automatic_trade_enabled);
        setAutomaticTradeLimit(String(loaded.automatic_trade_limit));
      })
      .catch((error) => {
        if (!(error instanceof DOMException && error.name === "AbortError")) {
          setFeedback({
            tone: "error",
            message: error instanceof Error ? error.message : "تعذر تحميل حدود المخاطر.",
          });
        }
      })
      .finally(() => setLoading(false));
    return () => controller.abort();
  }, [open]);

  async function handleSave() {
    const loss = Number(dailyLossLimit);
    const losing = Number(losingTradeLimit);
    const automatic = Number(automaticTradeLimit);
    if (dailyLossEnabled && (!Number.isFinite(loss) || loss <= 0)) {
      setFeedback({ tone: "warning", message: "Daily Equity-Loss Limit يجب أن يكون أكبر من صفر." });
      return;
    }
    if (losingTradeEnabled && (!Number.isInteger(losing) || losing < 1 || losing > 1000)) {
      setFeedback({ tone: "warning", message: "Daily Losing-Trades Limit يجب أن يكون عدداً صحيحاً بين 1 و1000." });
      return;
    }
    if (automaticTradeEnabled && (!Number.isInteger(automatic) || automatic < 1 || automatic > 100000)) {
      setFeedback({ tone: "warning", message: "Daily Automatic-Entry Limit يجب أن يكون عدداً صحيحاً بين 1 و100000." });
      return;
    }

    let confirmation = "";
    const weakensLivePolicy = policy && (
      (policy.daily_loss_enabled && !dailyLossEnabled)
      || (policy.losing_trade_enabled && !losingTradeEnabled)
      || (policy.automatic_trade_enabled && !automaticTradeEnabled)
    );
    if (weakensLivePolicy) {
      const accepted = window.confirm(
        "تعطيل Risk Policy Limit في LIVE قد يعرّض أموالاً حقيقية لخسارة أكبر. هذا لا يعطل Credentials أو Environment Matching أو Fresh Account Data أو Quantity أو Balance أو Protection-Order validation. هل تريد المتابعة؟",
      );
      if (!accepted) return;
      confirmation = window.prompt(
        "اكتب DISABLE LIVE RISK LIMITS لتأكيد تعطيل الحماية الاختيارية في LIVE.",
        "",
      ) ?? "";
      if (confirmation !== "DISABLE LIVE RISK LIMITS") {
        setFeedback({
          tone: "warning",
          message: "لم يتغير Risk Policy لأن عبارة تأكيد LIVE لم تكن مطابقة.",
        });
        return;
      }
    }

    setSaving(true);
    setFeedback(null);
    try {
      const saved = await saveAccountRiskPolicy({
        daily_loss_enabled: dailyLossEnabled,
        daily_loss_limit: Number.isFinite(loss) && loss > 0 ? dailyLossLimit : policy?.daily_loss_limit ?? "100",
        losing_trade_enabled: losingTradeEnabled,
        losing_trade_limit: Number.isInteger(losing) && losing >= 1 ? losing : policy?.losing_trade_limit ?? 3,
        automatic_trade_enabled: automaticTradeEnabled,
        automatic_trade_limit: Number.isInteger(automatic) && automatic >= 1 ? automatic : policy?.automatic_trade_limit ?? 5,
        confirmation,
      });
      setPolicy(saved);
      setDailyLossEnabled(saved.daily_loss_enabled);
      setDailyLossLimit(saved.daily_loss_limit);
      setLosingTradeEnabled(saved.losing_trade_enabled);
      setLosingTradeLimit(String(saved.losing_trade_limit));
      setAutomaticTradeEnabled(saved.automatic_trade_enabled);
      setAutomaticTradeLimit(String(saved.automatic_trade_limit));
      setFeedback({
        tone: "success",
        message: "حُفظ Risk Policy في SQLite، بما في ذلك حالة Enable/Disable الصريحة لكل Limit.",
      });
      onSaved();
    } catch (error) {
      setFeedback({
        tone: "error",
        message: error instanceof Error ? error.message : "تعذر حفظ حدود المخاطر.",
      });
    } finally {
      setSaving(false);
    }
  }

  if (!open) return null;

  return (
    <div className="drawer-layer" role="presentation">
      <button className="drawer-backdrop" type="button" onClick={onClose} aria-label="إغلاق إدارة المخاطر" />
      <section className="side-drawer risk-management-drawer" role="dialog" aria-modal="true" aria-labelledby="risk-management-title">
        <header className="drawer-header">
          <div>
            <span className="drawer-kicker">سياسة الحساب العامة</span>
            <h2 id="risk-management-title">إدارة المخاطر</h2>
          </div>
          <button className="icon-button" type="button" onClick={onClose} aria-label="إغلاق">
            <Icon name="x" />
          </button>
        </header>

        <div className="drawer-body drawer-stack">
          <div className="inline-alert warning-alert" role="note">
            <Icon name="shield" />
            <span>
              هذه Risk Policy مشتركة بين Testnet وLIVE. تعطيل أي Limit مفعّل يحتاج تأكيد LIVE حتى عند فتح الصفحة من Paper أو Testnet، ولا يعطل Environment Matching أو Credentials أو Fresh Account Data أو Balance أو Quantity أو unmanaged-state protection أو Protection Orders.
            </span>
          </div>

          <RiskLimitField
            checked={dailyLossEnabled}
            label="Enable Daily Equity-Loss Limit"
            description="يوقف Manual وAutomatic entries عند بلوغ الخسارة المقاسة من أول Equity baseline ثابت في يوم الرياض."
            unit="USDT"
            value={dailyLossLimit}
            inputMode="decimal"
            disabled={loading || saving}
            onToggle={setDailyLossEnabled}
            onValue={setDailyLossLimit}
          />

          <RiskLimitField
            checked={losingTradeEnabled}
            label="Enable Daily Losing-Trades Limit"
            description="يوقف Manual وAutomatic entries بعد عدد الإغلاقات الخاسرة المحدد."
            unit="Trades"
            value={losingTradeLimit}
            inputMode="numeric"
            disabled={loading || saving}
            onToggle={setLosingTradeEnabled}
            onValue={setLosingTradeLimit}
          />

          <RiskLimitField
            checked={automaticTradeEnabled}
            label="Enable Daily Automatic-Entry Limit"
            description="يوقف Automatic entries فقط عند بلوغ العدد؛ Manual entries تبقى خاضعة لبقية Safety Controls."
            unit="Entries"
            value={automaticTradeLimit}
            inputMode="numeric"
            disabled={loading || saving}
            onToggle={setAutomaticTradeEnabled}
            onValue={setAutomaticTradeLimit}
          />

          {environment === "live" && (
            <div className="inline-alert error-alert" role="note">
              <Icon name="alert" />
              <span>LIVE — REAL FUNDS: تعطيل أي Limit مفعّل يحتاج تحذيراً وتأكيداً حرفياً عند الحفظ.</span>
            </div>
          )}

          {policy && (
            <div className="connection-status-block">
              <div>
                <span className="connection-indicator ready" />
                <strong>الإصدار المحفوظ: {policy.revision}</strong>
              </div>
              <p>لن يظهر نجاح الحفظ إلا بعد أن يعيد المحرك السياسة الملتزم بها من SQLite.</p>
            </div>
          )}

          {feedback && (
            <div className={`inline-alert ${feedback.tone}-alert`} role={feedback.tone === "error" ? "alert" : "status"}>
              <Icon name={feedback.tone === "success" ? "shield" : "alert"} />
              <span>{feedback.message}</span>
            </div>
          )}

          <button className="primary-button" type="button" onClick={() => void handleSave()} disabled={loading || saving}>
            <Icon name="shield" />
            {saving ? "جارٍ الحفظ…" : loading ? "جارٍ التحميل…" : "حفظ Risk Policy"}
          </button>
        </div>
      </section>
    </div>
  );
}

function RiskLimitField({
  checked,
  label,
  description,
  unit,
  value,
  inputMode,
  disabled,
  onToggle,
  onValue,
}: {
  checked: boolean;
  label: string;
  description: string;
  unit: string;
  value: string;
  inputMode: "decimal" | "numeric";
  disabled: boolean;
  onToggle: (enabled: boolean) => void;
  onValue: (value: string) => void;
}) {
  return (
    <div className={`risk-limit-field ${checked ? "enabled" : "disabled"}`}>
      <label className="risk-limit-toggle">
        <input
          type="checkbox"
          checked={checked}
          disabled={disabled}
          onChange={(event) => onToggle(event.target.checked)}
        />
        <span className="risk-toggle-track" aria-hidden="true"><span /></span>
        <span>
          <strong>{label}</strong>
          <small>{checked ? "Enabled — not evaluated until current risk data is ready." : "Disabled — this optional Limit will not block entries."}</small>
        </span>
      </label>
      <label className="field-block">
        <span>Limit Value ({unit})</span>
        <input
          dir="ltr"
          inputMode={inputMode}
          value={value}
          onChange={(event) => onValue(event.target.value)}
          disabled={disabled || !checked}
          aria-disabled={disabled || !checked}
        />
        <small>{description}</small>
      </label>
    </div>
  );
}
