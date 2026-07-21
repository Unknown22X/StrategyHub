import { useEffect, useState } from "react";

import {
  loadCredentialStatus,
  removeCredentials,
  saveCredentials,
  testCredentials,
} from "../api";
import type {
  ExchangeCredentialStatus,
  ExchangeCredentialTestResult,
} from "../types";
import { Icon } from "./Icon";

interface GateConnectionDrawerProps {
  open: boolean;
  initialMode: "live" | "testnet";
  onClose: () => void;
  onChanged: () => void;
}

type Feedback =
  | { tone: "success" | "warning" | "error"; message: string }
  | null;

export function GateConnectionDrawer({
  open,
  initialMode,
  onClose,
  onChanged,
}: GateConnectionDrawerProps) {
  const [mode, setMode] = useState<"live" | "testnet">(initialMode);
  const [status, setStatus] = useState<ExchangeCredentialStatus | null>(null);
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState<"save" | "test" | "remove" | null>(null);
  const [apiKey, setApiKey] = useState("");
  const [apiSecret, setApiSecret] = useState("");
  const [feedback, setFeedback] = useState<Feedback>(null);

  useEffect(() => {
    if (!open) {
      return;
    }
    setMode(initialMode);
  }, [initialMode, open]);

  useEffect(() => {
    if (!open) {
      return;
    }
    const controller = new AbortController();
    setLoading(true);
    setFeedback(null);
    loadCredentialStatus(mode, controller.signal)
      .then(setStatus)
      .catch((error) => {
        if (!(error instanceof DOMException && error.name === "AbortError")) {
          setFeedback({
            tone: "error",
            message: error instanceof Error ? error.message : "تعذر تحميل حالة بيانات Gate.io.",
          });
        }
      })
      .finally(() => setLoading(false));
    return () => controller.abort();
  }, [mode, open]);

  async function handleSave() {
    if (!apiKey.trim() || !apiSecret.trim()) {
      setFeedback({ tone: "warning", message: "أدخل مفتاح API والسر قبل الحفظ." });
      return;
    }
    setBusy("save");
    setFeedback(null);
    try {
      const saved = await saveCredentials(mode, apiKey.trim(), apiSecret.trim());
      setStatus(saved);
      setApiKey("");
      setApiSecret("");
      setFeedback({
        tone: "success",
        message: "حُفظت بيانات Gate.io في مخزن Windows المحمي، وأُعيدت تهيئة اتصال الحساب.",
      });
      onChanged();
    } catch (error) {
      setFeedback({
        tone: "error",
        message: error instanceof Error ? error.message : "تعذر حفظ بيانات Gate.io.",
      });
    } finally {
      setBusy(null);
    }
  }

  async function handleTest() {
    setBusy("test");
    setFeedback(null);
    try {
      const result: ExchangeCredentialTestResult = await testCredentials(mode);
      setFeedback({
        tone: result.valid ? "success" : "warning",
        message: result.message_ar,
      });
    } catch (error) {
      setFeedback({
        tone: "error",
        message: error instanceof Error ? error.message : "تعذر اختبار بيانات Gate.io.",
      });
    } finally {
      setBusy(null);
    }
  }

  async function handleRemove() {
    const confirmed = window.confirm(
      `إزالة بيانات ${mode === "live" ? "Live" : "Testnet"} المحمية؟ سيتم حظر التداول حتى حفظ بيانات جديدة وإتمام المصالحة.`,
    );
    if (!confirmed) {
      return;
    }
    setBusy("remove");
    setFeedback(null);
    try {
      const removed = await removeCredentials(mode);
      setStatus(removed);
      setApiKey("");
      setApiSecret("");
      setFeedback({
        tone: "success",
        message: "أُزيلت البيانات المحمية وأُبطلت لقطة الحساب السابقة.",
      });
      onChanged();
    } catch (error) {
      setFeedback({
        tone: "error",
        message: error instanceof Error ? error.message : "تعذر إزالة بيانات Gate.io.",
      });
    } finally {
      setBusy(null);
    }
  }

  if (!open) {
    return null;
  }

  return (
    <div className="drawer-layer" role="presentation">
      <button className="drawer-backdrop" type="button" onClick={onClose} aria-label="إغلاق إعدادات Gate.io" />
      <section className="side-drawer connection-drawer" role="dialog" aria-modal="true" aria-labelledby="gate-connection-title">
        <header className="drawer-header">
          <div>
            <span className="drawer-kicker">اتصال الحساب المحمي</span>
            <h2 id="gate-connection-title">Gate.io Futures</h2>
          </div>
          <button className="icon-button" type="button" onClick={onClose} aria-label="إغلاق">
            <Icon name="x" />
          </button>
        </header>

        <div className="drawer-body drawer-stack">
          <div className="mode-segment" aria-label="بيئة بيانات الاعتماد">
            <button
              className={mode === "live" ? "active danger-segment" : ""}
              type="button"
              onClick={() => setMode("live")}
            >
              Live
            </button>
            <button
              className={mode === "testnet" ? "active" : ""}
              type="button"
              onClick={() => setMode("testnet")}
            >
              Testnet
            </button>
          </div>
          <p className="credential-profile-note">
            هذا الاختيار يحدد Credential Profile الذي تعدّله فقط. تغيير بيئة التداول الفعلية يتم من شريط البيئة الرئيسي.
          </p>

          <div className="connection-status-block">
            <div>
              <span className={`connection-indicator ${status?.configured ? "ready" : "missing"}`} />
              <strong>{loading ? "جارٍ التحقق…" : status?.configured ? "بيانات محمية محفوظة" : "لا توجد بيانات محفوظة"}</strong>
            </div>
            <p>
              لا يعيد المحرك المفتاح أو السر إلى الواجهة. الحفظ والاستبدال يتمان داخل مخزن Windows المحمي فقط.
            </p>
          </div>

          {mode === "live" && (
            <div className="inline-alert warning-alert" role="note">
              <Icon name="alert" />
              <span>هذه البيانات تسمح باستخدام أموال حقيقية بعد اجتياز المصالحة وحدود المخاطر.</span>
            </div>
          )}

          <label className="field-block">
            <span>Gate API Key</span>
            <input
              autoComplete="off"
              inputMode="text"
              value={apiKey}
              onChange={(event) => setApiKey(event.target.value)}
              placeholder="أدخل المفتاح الجديد أو البديل"
            />
            <small>لن يظهر المفتاح الكامل مرة أخرى بعد الحفظ.</small>
          </label>

          <label className="field-block">
            <span>Gate API Secret</span>
            <input
              autoComplete="new-password"
              type="password"
              value={apiSecret}
              onChange={(event) => setApiSecret(event.target.value)}
              placeholder="أدخل السر"
            />
            <small>لا تمنح المفتاح صلاحية السحب.</small>
          </label>

          {feedback && (
            <div className={`inline-alert ${feedback.tone}-alert`} role={feedback.tone === "error" ? "alert" : "status"}>
              <Icon name={feedback.tone === "success" ? "shield" : "alert"} />
              <span>{feedback.message}</span>
            </div>
          )}

          <div className="drawer-action-grid">
            <button className="primary-button" type="button" onClick={() => void handleSave()} disabled={busy !== null}>
              <Icon name="shield" />
              {busy === "save" ? "جارٍ الحفظ…" : status?.configured ? "استبدال البيانات" : "حفظ البيانات"}
            </button>
            <button className="secondary-button" type="button" onClick={() => void handleTest()} disabled={busy !== null || !status?.configured}>
              <Icon name="activity" />
              {busy === "test" ? "جارٍ الاختبار…" : "اختبار للقراءة فقط"}
            </button>
            <button className="danger-button" type="button" onClick={() => void handleRemove()} disabled={busy !== null || !status?.configured}>
              <Icon name="x" />
              {busy === "remove" ? "جارٍ الإزالة…" : "إزالة البيانات"}
            </button>
          </div>
        </div>
      </section>
    </div>
  );
}
