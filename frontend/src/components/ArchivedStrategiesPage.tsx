import { useEffect, useState } from "react";

import {
  deleteStrategy,
  loadArchivedStrategies,
  loadStrategyDeletionReadiness,
  restoreStrategy,
} from "../api";
import type { RemoteData, StrategyDeletionReadiness, StrategyInstance } from "../types";
import { formatDateTime } from "../lib/format";
import { Icon } from "./Icon";
import { StateView, StatusPill } from "./StateView";

interface ArchivedStrategiesPageProps {
  onRestored: (strategy: StrategyInstance) => void;
  onDeleted: (instanceId: string) => void;
}

export function ArchivedStrategiesPage({
  onRestored,
  onDeleted,
}: ArchivedStrategiesPageProps) {
  const [strategies, setStrategies] = useState<RemoteData<StrategyInstance[]>>({ status: "loading" });
  const [readiness, setReadiness] = useState<Record<string, StrategyDeletionReadiness>>({});
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    setStrategies({ status: "loading" });
    loadArchivedStrategies(controller.signal)
      .then(async (items) => {
        setStrategies({ status: "ready", data: items });
        const results = await Promise.all(
          items.map(async (item) => [
            item.instance_id,
            await loadStrategyDeletionReadiness(item.instance_id, controller.signal),
          ] as const),
        );
        setReadiness(Object.fromEntries(results));
      })
      .catch((reason: unknown) => {
        if (controller.signal.aborted) return;
        setStrategies({
          status: "error",
          message: reason instanceof Error ? reason.message : "تعذر تحميل Archived Strategies.",
        });
      });
    return () => controller.abort();
  }, []);

  async function restore(item: StrategyInstance) {
    setBusy(`${item.instance_id}:restore`);
    setError(null);
    try {
      const restored = await restoreStrategy(item.instance_id);
      setStrategies((current) => current.status === "ready"
        ? { status: "ready", data: current.data.filter((value) => value.instance_id !== item.instance_id) }
        : current);
      onRestored(restored);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "تعذر Restore Strategy.");
    } finally {
      setBusy(null);
    }
  }

  async function remove(item: StrategyInstance) {
    const state = readiness[item.instance_id];
    if (!state?.can_delete) return;
    if (!window.confirm(`حذف ${item.name} نهائياً؟ لا يمكن التراجع عن هذا الإجراء.`)) return;
    setBusy(`${item.instance_id}:delete`);
    setError(null);
    try {
      await deleteStrategy(item.instance_id);
      setStrategies((current) => current.status === "ready"
        ? { status: "ready", data: current.data.filter((value) => value.instance_id !== item.instance_id) }
        : current);
      onDeleted(item.instance_id);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "تعذر حذف Strategy.");
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="dashboard-content archived-strategies-page">
      <header className="page-heading">
        <div>
          <span className="eyebrow">Strategy history</span>
          <h1>Archived Strategies</h1>
          <p>يمكن Restore أي Strategy. الحذف النهائي متاح فقط للـ Instances غير المستخدمة.</p>
        </div>
      </header>

      {error && <div className="inline-alert error-alert" role="alert"><Icon name="alert" /><span>{error}</span></div>}

      <StateView value={strategies} unavailableLabel="تعذر تحميل Archived Strategies">
        {(items) => items.length === 0 ? (
          <div className="empty-state panel">
            <Icon name="archive" size={32} />
            <h2>لا توجد Archived Strategies</h2>
            <p>عند Archive Strategy ستظهر هنا ويمكن Restoreها لاحقاً.</p>
          </div>
        ) : (
          <div className="strategy-grid">
            {items.map((item) => {
              const deletion = readiness[item.instance_id];
              return (
                <article className="panel strategy-card" key={item.instance_id}>
                  <div className="panel-header">
                    <div>
                      <h2>{item.name}</h2>
                      <p>{item.symbol} · {item.timeframe_minutes}m · {item.environment.toUpperCase()}</p>
                    </div>
                    <StatusPill label="Archived" tone="neutral" />
                  </div>
                  <dl className="compact-details">
                    <div><dt>Archived at</dt><dd>{item.archived_at ? formatDateTime(item.archived_at) : "—"}</dd></div>
                    <div><dt>Reason</dt><dd>{item.archive_reason || "بدون سبب محفوظ"}</dd></div>
                  </dl>
                  {deletion && !deletion.can_delete && (
                    <div className="inline-alert neutral-alert" role="note">
                      <Icon name="shield" />
                      <span>الحذف غير متاح لأن سجل التشغيل أو التداول يجب أن يبقى محفوظاً.</span>
                    </div>
                  )}
                  <div className="card-actions">
                    <button
                      className="primary-button"
                      type="button"
                      disabled={busy !== null}
                      onClick={() => void restore(item)}
                    >
                      <Icon name="refresh" /> Restore
                    </button>
                    <button
                      className="danger-button"
                      type="button"
                      disabled={busy !== null || !deletion?.can_delete}
                      title={!deletion?.can_delete ? "هذه Strategy تحتوي على history ويجب إبقاؤها Archived." : undefined}
                      onClick={() => void remove(item)}
                    >
                      <Icon name="x" /> Delete permanently
                    </button>
                  </div>
                </article>
              );
            })}
          </div>
        )}
      </StateView>
    </div>
  );
}
