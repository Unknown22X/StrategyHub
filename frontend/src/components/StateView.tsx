import type { ReactNode } from "react";

import type { RemoteData } from "../types";

interface StateViewProps<T> {
  value?: RemoteData<T>;
  state?: RemoteData<T>;
  children: (data: T) => ReactNode;
  compact?: boolean;
  unavailableLabel?: string;
  loadingLabel?: string;
}

export function StateView<T>({
  value,
  state,
  children,
  compact = false,
  unavailableLabel = "البيانات غير متاحة",
}: StateViewProps<T>) {
  const remoteData = value ?? state;
  if (!remoteData) return null;
  if (remoteData.status === "loading") {
    return (
      <div className={compact ? "state-line" : "state-panel"} role="status">
        <span className="skeleton-dot" />
        جارٍ تحميل البيانات…
      </div>
    );
  }
  if (remoteData.status === "error") {
    return (
      <div className={compact ? "state-line state-error" : "state-panel state-error"}>
        <strong>{unavailableLabel}</strong>
        {!compact && <span>{remoteData.message}</span>}
      </div>
    );
  }
  return children(remoteData.data);
}

interface StatusPillProps {
  label?: string;
  children?: ReactNode;
  tone?: "positive" | "negative" | "warning" | "neutral" | "info";
  pulse?: boolean;
}

export function StatusPill({
  label,
  children,
  tone = "neutral",
  pulse = false,
}: StatusPillProps) {
  return (
    <span className={`status-pill status-${tone}`}>
      <span className={pulse ? "status-dot status-dot-pulse" : "status-dot"} />
      {label ?? children}
    </span>
  );
}

interface EmptyStateProps {
  title: string;
  description: string;
  action?: ReactNode;
  icon?: string;
}

export function EmptyState({ title, description, action }: EmptyStateProps) {
  return (
    <div className="empty-state">
      <div className="empty-state-mark" aria-hidden="true" />
      <strong>{title}</strong>
      <span>{description}</span>
      {action}
    </div>
  );
}
