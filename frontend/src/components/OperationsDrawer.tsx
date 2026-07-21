import { useEffect, useState } from "react";

import {
  createBackup,
  deleteBackup,
  exportSupportLogs,
  listBackups,
  restoreBackup,
} from "../api";
import { formatDateTime } from "../lib/format";
import type { BackupKind, BackupRecord, RemoteData } from "../types";
import { Icon } from "./Icon";
import { StateView } from "./StateView";


interface OperationsDrawerProps {
  open: boolean;
  onClose: () => void;
  onRestored: () => void;
}

const backupKindLabels: Record<BackupKind, string> = {
  manual: "يدوية",
  pre_migration: "قبل الترحيل",
  pre_restore: "أمان قبل الاستعادة",
  lifecycle: "دورة حياة",
};

export function OperationsDrawer({
  open,
  onClose,
  onRestored,
}: OperationsDrawerProps) {
  const [backups, setBackups] = useState<RemoteData<BackupRecord[]>>({
    status: "loading",
  });
  const [busy, setBusy] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) {
      return;
    }
    const controller = new AbortController();
    setBackups({ status: "loading" });
    listBackups(controller.signal)
      .then((items) => setBackups({ status: "ready", data: items }))
      .catch((caught) => {
        if (!(caught instanceof DOMException && caught.name === "AbortError")) {
          setBackups({
            status: "error",
            message: caught instanceof Error ? caught.message : "تعذر تحميل النسخ الاحتياطية.",
          });
        }
      });
    return () => controller.abort();
  }, [open]);

  if (!open) {
    return null;
  }

  async function refreshBackups() {
    setBackups({ status: "loading" });
    try {
      setBackups({ status: "ready", data: await listBackups() });
    } catch (caught) {
      setBackups({
        status: "error",
        message: caught instanceof Error ? caught.message : "تعذر تحميل النسخ الاحتياطية.",
      });
    }
  }

  async function handleCreate() {
    setBusy("create");
    setError(null);
    setMessage(null);
    try {
      const created = await createBackup();
      setMessage(`تم إنشاء النسخة ${created.name} بعد تأكيد المحرك.`);
      await refreshBackups();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "تعذر إنشاء النسخة الاحتياطية.");
    } finally {
      setBusy(null);
    }
  }

  async function handleDelete(backup: BackupRecord) {
    if (!window.confirm(`حذف النسخة ${backup.name} نهائياً؟`)) {
      return;
    }
    setBusy(`delete:${backup.name}`);
    setError(null);
    setMessage(null);
    try {
      const result = await deleteBackup(backup.name);
      setMessage(result.message_ar);
      await refreshBackups();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "تعذر حذف النسخة الاحتياطية.");
    } finally {
      setBusy(null);
    }
  }

  async function handleRestore(backup: BackupRecord) {
    const confirmation = window.prompt(
      `لاستعادة ${backup.name}، اكتب RESTORE RANGEBOT حرفياً. سيوقف المحرك الاستراتيجيات ويُبقي الإيقاف الطارئ نشطاً.`,
    );
    if (confirmation === null) {
      return;
    }
    if (confirmation !== "RESTORE RANGEBOT") {
      setError("نص تأكيد الاستعادة غير مطابق.");
      return;
    }
    setBusy(`restore:${backup.name}`);
    setError(null);
    setMessage(null);
    try {
      const result = await restoreBackup(backup.name);
      setMessage(result.message_ar);
      await refreshBackups();
      onRestored();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "تعذر استعادة النسخة الاحتياطية.");
    } finally {
      setBusy(null);
    }
  }

  async function handleLogExport() {
    setBusy("logs");
    setError(null);
    setMessage(null);
    try {
      const archive = await exportSupportLogs();
      const url = URL.createObjectURL(archive.blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = archive.filename;
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(url);
      setMessage("تم إنشاء وتنزيل حزمة السجلات المنقحة.");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "تعذر تصدير السجلات.");
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="drawer-backdrop" role="presentation" onMouseDown={onClose}>
      <aside
        aria-label="النسخ الاحتياطية وسجلات الدعم"
        aria-modal="true"
        className="trade-drawer operations-drawer"
        role="dialog"
        onMouseDown={(event) => event.stopPropagation()}
      >
        <header className="drawer-header">
          <div>
            <span className="eyebrow">البيانات المحلية والدعم</span>
            <h2>النسخ الاحتياطية والسجلات</h2>
            <p>كل عملية تنفذ داخل المحرك وتظهر ناجحة فقط بعد اكتمالها فعلياً.</p>
          </div>
          <button className="icon-button" type="button" onClick={onClose} aria-label="إغلاق">
            <Icon name="x" />
          </button>
        </header>

        <div className="operations-actions">
          <button
            className="primary-button"
            type="button"
            disabled={busy !== null}
            onClick={() => void handleCreate()}
          >
            <Icon name="archive" />
            {busy === "create" ? "جارٍ إنشاء النسخة..." : "إنشاء نسخة آمنة"}
          </button>
          <button
            className="secondary-button"
            type="button"
            disabled={busy !== null}
            onClick={() => void handleLogExport()}
          >
            <Icon name="activity" />
            {busy === "logs" ? "جارٍ تجهيز السجلات..." : "تصدير سجلات الدعم"}
          </button>
        </div>

        {message && <div className="inline-alert success-alert" role="status">{message}</div>}
        {error && <div className="inline-alert error-alert" role="alert">{error}</div>}

        <section className="operations-section">
          <div className="panel-header">
            <div>
              <span className="eyebrow">الاحتفاظ: أحدث 10 نسخ</span>
              <h3>النسخ المتاحة</h3>
            </div>
            <button
              className="icon-button"
              type="button"
              disabled={busy !== null}
              onClick={() => void refreshBackups()}
              aria-label="تحديث النسخ"
            >
              <Icon name="refresh" />
            </button>
          </div>

          <StateView value={backups}>
            {(items) => items.length === 0 ? (
              <div className="empty-state compact-empty">
                <Icon name="archive" size={24} />
                <strong>لا توجد نسخ احتياطية بعد</strong>
                <span>أنشئ نسخة يدوية قبل تغيير إعدادات مهمة.</span>
              </div>
            ) : (
              <div className="backup-list">
                {items.map((backup) => (
                  <article className="backup-item" key={backup.name}>
                    <div className="backup-copy">
                      <strong>{backupKindLabels[backup.kind]}</strong>
                      <span>{formatDateTime(backup.created_at)}</span>
                      <small>{formatBytes(backup.size_bytes)} · {backup.name}</small>
                    </div>
                    <div className="backup-actions">
                      <button
                        className="secondary-button compact-button"
                        type="button"
                        disabled={busy !== null}
                        onClick={() => void handleRestore(backup)}
                      >
                        {busy === `restore:${backup.name}` ? "جارٍ الاستعادة..." : "استعادة"}
                      </button>
                      <button
                        className="danger-button compact-button"
                        type="button"
                        disabled={busy !== null}
                        onClick={() => void handleDelete(backup)}
                      >
                        {busy === `delete:${backup.name}` ? "جارٍ الحذف..." : "حذف"}
                      </button>
                    </div>
                  </article>
                ))}
              </div>
            )}
          </StateView>
        </section>
      </aside>
    </div>
  );
}

function formatBytes(value: number): string {
  if (value < 1024) {
    return `${value} B`;
  }
  if (value < 1024 * 1024) {
    return `${(value / 1024).toFixed(1)} KB`;
  }
  return `${(value / (1024 * 1024)).toFixed(1)} MB`;
}
