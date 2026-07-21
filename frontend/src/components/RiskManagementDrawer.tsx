import { useEffect, useState } from "react";

import { loadAccountRiskPolicy, saveAccountRiskPolicy } from "../api";
import type { AccountRiskPolicy } from "../types";
import { Icon } from "./Icon";

interface RiskManagementDrawerProps {
  open: boolean;
  onClose: () => void;
  onSaved: () => void;
}

type Feedback = { tone: "success" | "warning" | "error"; message: string } | null;

export function RiskManagementDrawer({
  open,
  onClose,
  onSaved,
}: RiskManagementDrawerProps) {
  const [policy, setPolicy] = useState<AccountRiskPolicy | null>(null);
  const [dailyLossLimit, setDailyLossLimit] = useState("100");
  const [losingTradeLimit, setLosingTradeLimit] = useState("3");
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
        setDailyLossLimit(loaded.daily_loss_limit);
        setLosingTradeLimit(String(loaded.losing_trade_limit));
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
    if (!Number.isFinite(loss) || loss <= 0) {
      setFeedback({ tone: "warning", message: "حد الخسارة اليومية يجب أن يكون أكبر من صفر." });
      return;
    }
    if (!Number.isInteger(losing) || losing < 1 || losing > 1000) {
      setFeedback({ tone: "warning", message: "حد الصفقات الخاسرة يجب أن يكون عدداً صحيحاً بين 1 و1000." });
      return;
    }
    if (!Number.isInteger(automatic) || automatic < 1 || automatic > 100000) {
      setFeedback({ tone: "warning", message: "حد الصفقات التلقائية يجب أن يكون عدداً صحيحاً بين 1 و100000." });
      return;
    }

    setSaving(true);
    setFeedback(null);
    try {
      const saved = await saveAccountRiskPolicy({
        daily_loss_limit: dailyLossLimit,
        losing_trade_limit: losing,
        automatic_trade_limit: automatic,
      });
      setPolicy(saved);
      setDailyLossLimit(saved.daily_loss_limit);
      setLosingTradeLimit(String(saved.losing_trade_limit));
      setAutomaticTradeLimit(String(saved.automatic_trade_limit));
      setFeedback({
        tone: "success",
        message: "حُفظت حدود المخاطر في قاعدة البيانات وأصبحت نافذة على الإدخالات الجديدة.",
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
              تطبق هذه الحدود على Testnet وLive. التداول اليدوي يحترم الخسارة اليومية والصفقات الخاسرة؛ التداول التلقائي يحترمها إضافة إلى حد الصفقات التلقائية.
            </span>
          </div>

          <label className="field-block">
            <span>حد خسارة حقوق الملكية اليومية (USDT)</span>
            <input
              dir="ltr"
              inputMode="decimal"
              value={dailyLossLimit}
              onChange={(event) => setDailyLossLimit(event.target.value)}
              disabled={loading || saving}
            />
            <small>يُقاس من أول لقطة حقوق ملكية موثوقة في يوم الرياض.</small>
          </label>

          <label className="field-block">
            <span>الحد اليومي للصفقات الخاسرة</span>
            <input
              dir="ltr"
              inputMode="numeric"
              value={losingTradeLimit}
              onChange={(event) => setLosingTradeLimit(event.target.value)}
              disabled={loading || saving}
            />
            <small>يُحسب كل أمر إغلاق خاسر مرة واحدة حتى مع وجود عدة تعبئات.</small>
          </label>

          <label className="field-block">
            <span>الحد اليومي للدخولات التلقائية</span>
            <input
              dir="ltr"
              inputMode="numeric"
              value={automaticTradeLimit}
              onChange={(event) => setAutomaticTradeLimit(event.target.value)}
              disabled={loading || saving}
            />
            <small>لا يقيّد الإدخالات اليدوية، لكنه يمنع الاستراتيجيات التلقائية بعد بلوغه.</small>
          </label>

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
            {saving ? "جارٍ الحفظ…" : loading ? "جارٍ التحميل…" : "حفظ حدود المخاطر"}
          </button>
        </div>
      </section>
    </div>
  );
}
