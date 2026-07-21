import { useEffect, useMemo, useState } from "react";

import {
  defaultDashboardFilters,
  type DashboardFilters,
} from "../dashboardFilters";
import type { Environment, StrategyInstance } from "../types";
import { Icon } from "./Icon";

interface DashboardFilterBarProps {
  filters: DashboardFilters;
  currentEnvironment: Environment | null;
  strategies: StrategyInstance[];
  symbols: string[];
  onSave: (filters: DashboardFilters) => Promise<void>;
}

type Feedback = { tone: "success" | "error"; message: string } | null;

export function DashboardFilterBar({
  filters,
  currentEnvironment,
  strategies,
  symbols,
  onSave,
}: DashboardFilterBarProps) {
  const [draft, setDraft] = useState(filters);
  const [busy, setBusy] = useState(false);
  const [feedback, setFeedback] = useState<Feedback>(null);

  useEffect(() => {
    setDraft(filters);
  }, [filters]);

  const strategyOptions = useMemo(
    () => [...strategies].sort((a, b) => a.name.localeCompare(b.name, "ar")),
    [strategies],
  );

  async function persist(next: DashboardFilters, successMessage: string) {
    setBusy(true);
    setFeedback(null);
    try {
      await onSave(next);
      setDraft(next);
      setFeedback({ tone: "success", message: successMessage });
    } catch (error) {
      setFeedback({
        tone: "error",
        message: error instanceof Error ? error.message : "تعذر حفظ فلاتر لوحة العمليات.",
      });
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="dashboard-filter-bar" aria-label="فلاتر لوحة العمليات">
      <div className="dashboard-filter-fields">
        <label>
          <span>بيئة العرض</span>
          <select
            value={draft.environment}
            onChange={(event) => setDraft((current) => ({
              ...current,
              environment: event.target.value as DashboardFilters["environment"],
            }))}
          >
            <option value="current">الحالية ({currentEnvironment?.toUpperCase() ?? "—"})</option>
            <option value="live">Live</option>
            <option value="testnet">Testnet</option>
            <option value="paper">Paper</option>
          </select>
        </label>

        <label>
          <span>الاستراتيجية</span>
          <select
            value={draft.strategyId ?? ""}
            onChange={(event) => setDraft((current) => ({
              ...current,
              strategyId: event.target.value || null,
            }))}
          >
            <option value="">كل الاستراتيجيات</option>
            {strategyOptions.map((strategy) => (
              <option key={strategy.instance_id} value={strategy.instance_id}>
                {strategy.name}
              </option>
            ))}
          </select>
        </label>

        <label>
          <span>العقد</span>
          <select
            value={draft.symbol ?? ""}
            onChange={(event) => setDraft((current) => ({
              ...current,
              symbol: event.target.value || null,
            }))}
          >
            <option value="">كل العقود</option>
            {symbols.map((symbol) => <option key={symbol} value={symbol}>{symbol}</option>)}
          </select>
        </label>

        <label>
          <span>الفترة</span>
          <select
            value={draft.period}
            onChange={(event) => setDraft((current) => ({
              ...current,
              period: event.target.value as DashboardFilters["period"],
            }))}
          >
            <option value="today">اليوم</option>
            <option value="7d">7 أيام</option>
            <option value="30d">30 يوماً</option>
            <option value="all">الكل</option>
          </select>
        </label>

        <label>
          <span>نوع النشاط</span>
          <select
            value={draft.eventType}
            onChange={(event) => setDraft((current) => ({
              ...current,
              eventType: event.target.value as DashboardFilters["eventType"],
            }))}
          >
            <option value="all">كل النشاط</option>
            <option value="decision">قرارات الاستراتيجيات</option>
            <option value="strategy">حالات الاستراتيجيات</option>
            <option value="order">الطلبات والتنفيذ</option>
            <option value="paper">أحداث Paper</option>
            <option value="risk">المخاطر والحماية</option>
            <option value="system">المحرك والنظام</option>
            <option value="research">الفحص والاختبارات التاريخية</option>
          </select>
        </label>
      </div>

      <div className="dashboard-filter-actions">
        <button className="primary-button" type="button" disabled={busy} onClick={() => void persist(draft, "حفظ المحرك فلاتر لوحة العمليات.")}>
          <Icon name="settings" />
          {busy ? "جارٍ الحفظ…" : "تطبيق وحفظ"}
        </button>
        <button className="secondary-button" type="button" disabled={busy} onClick={() => void persist(defaultDashboardFilters, "أعاد المحرك فلاتر العرض الافتراضية.")}>
          <Icon name="x" />
          إعادة الضبط
        </button>
      </div>

      {feedback && (
        <div className={`dashboard-filter-feedback ${feedback.tone}`} role={feedback.tone === "error" ? "alert" : "status"}>
          {feedback.message}
        </div>
      )}
    </section>
  );
}
