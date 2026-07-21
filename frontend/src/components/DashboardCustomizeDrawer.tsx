import { useEffect, useState } from "react";

import {
  dashboardWidgetLabels,
  defaultDashboardLayout,
  type DashboardLayoutSettings,
  type DashboardWidgetId,
} from "../dashboardLayout";
import { Icon } from "./Icon";

interface DashboardCustomizeDrawerProps {
  open: boolean;
  layout: DashboardLayoutSettings;
  onClose: () => void;
  onSave: (layout: DashboardLayoutSettings) => Promise<void>;
}

type Feedback = { tone: "success" | "error"; message: string } | null;

export function DashboardCustomizeDrawer({
  open,
  layout,
  onClose,
  onSave,
}: DashboardCustomizeDrawerProps) {
  const [draft, setDraft] = useState(layout);
  const [busy, setBusy] = useState(false);
  const [feedback, setFeedback] = useState<Feedback>(null);

  useEffect(() => {
    if (open) {
      setDraft(layout);
      setFeedback(null);
    }
  }, [layout, open]);

  if (!open) {
    return null;
  }

  function toggleWidget(widget: DashboardWidgetId) {
    setDraft((current) => ({
      ...current,
      hidden: current.hidden.includes(widget)
        ? current.hidden.filter((item) => item !== widget)
        : [...current.hidden, widget],
    }));
  }

  function moveWidget(widget: DashboardWidgetId, offset: -1 | 1) {
    setDraft((current) => {
      const index = current.order.indexOf(widget);
      const target = index + offset;
      if (index < 0 || target < 0 || target >= current.order.length) {
        return current;
      }
      const order = [...current.order];
      [order[index], order[target]] = [order[target], order[index]];
      return { ...current, order };
    });
  }

  async function persist(next: DashboardLayoutSettings, successMessage: string) {
    setBusy(true);
    setFeedback(null);
    try {
      await onSave(next);
      setDraft(next);
      setFeedback({ tone: "success", message: successMessage });
    } catch (error) {
      setFeedback({
        tone: "error",
        message: error instanceof Error ? error.message : "تعذر حفظ تخطيط لوحة العمليات.",
      });
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="drawer-layer" role="presentation">
      <button className="drawer-backdrop" type="button" onClick={onClose} aria-label="إغلاق تخصيص لوحة العمليات" />
      <section className="side-drawer dashboard-customize-drawer" role="dialog" aria-modal="true" aria-labelledby="dashboard-customize-title">
        <header className="drawer-header">
          <div>
            <span className="drawer-kicker">محفوظ في المحرك</span>
            <h2 id="dashboard-customize-title">تخصيص لوحة العمليات</h2>
          </div>
          <button className="icon-button" type="button" onClick={onClose} aria-label="إغلاق">
            <Icon name="x" />
          </button>
        </header>

        <div className="drawer-body drawer-stack">
          <section className="customize-section">
            <div className="section-title-row">
              <div>
                <h3>الكثافة</h3>
                <p>غيّر المسافات من دون إخفاء أي بيانات.</p>
              </div>
            </div>
            <div className="mode-segment">
              <button
                className={draft.density === "compact" ? "active" : ""}
                type="button"
                onClick={() => setDraft((current) => ({ ...current, density: "compact" }))}
              >
                مضغوط
              </button>
              <button
                className={draft.density === "comfortable" ? "active" : ""}
                type="button"
                onClick={() => setDraft((current) => ({ ...current, density: "comfortable" }))}
              >
                مريح
              </button>
            </div>
          </section>

          <section className="customize-section">
            <div className="section-title-row">
              <div>
                <h3>الأقسام والترتيب</h3>
                <p>الإخفاء والترتيب يظلان محفوظين بعد إغلاق الواجهة أو إعادة التشغيل.</p>
              </div>
            </div>
            <div className="widget-order-list">
              {draft.order.map((widget, index) => {
                const hidden = draft.hidden.includes(widget);
                return (
                  <div className={hidden ? "widget-order-row hidden-widget" : "widget-order-row"} key={widget}>
                    <label>
                      <input
                        type="checkbox"
                        checked={!hidden}
                        onChange={() => toggleWidget(widget)}
                      />
                      <span>{dashboardWidgetLabels[widget]}</span>
                    </label>
                    <div className="widget-move-actions">
                      <button
                        className="icon-button move-up"
                        type="button"
                        disabled={index === 0}
                        onClick={() => moveWidget(widget, -1)}
                        aria-label={`نقل ${dashboardWidgetLabels[widget]} إلى أعلى`}
                      >
                        <Icon name="chevron" size={17} />
                      </button>
                      <button
                        className="icon-button move-down"
                        type="button"
                        disabled={index === draft.order.length - 1}
                        onClick={() => moveWidget(widget, 1)}
                        aria-label={`نقل ${dashboardWidgetLabels[widget]} إلى أسفل`}
                      >
                        <Icon name="chevron" size={17} />
                      </button>
                    </div>
                  </div>
                );
              })}
            </div>
          </section>

          {feedback && (
            <div className={`inline-alert ${feedback.tone}-alert`} role={feedback.tone === "error" ? "alert" : "status"}>
              <Icon name={feedback.tone === "success" ? "shield" : "alert"} />
              <span>{feedback.message}</span>
            </div>
          )}

          <div className="drawer-action-grid">
            <button className="primary-button" type="button" disabled={busy} onClick={() => void persist(draft, "حفظ المحرك تخطيط لوحة العمليات.")}>
              <Icon name="shield" />
              {busy ? "جارٍ الحفظ…" : "حفظ التخطيط"}
            </button>
            <button className="secondary-button" type="button" disabled={busy} onClick={() => void persist(defaultDashboardLayout, "أعاد المحرك التخطيط الافتراضي.")}>
              <Icon name="settings" />
              إعادة التخطيط الافتراضي
            </button>
          </div>
        </div>
      </section>
    </div>
  );
}
