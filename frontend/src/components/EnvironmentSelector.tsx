import type { Environment, EnvironmentRuntimeState } from "../types";
import { Icon } from "./Icon";
import { StatusPill } from "./StateView";

interface EnvironmentSelectorProps {
  runtime: EnvironmentRuntimeState | null;
  busy: boolean;
  onChange: (environment: Environment) => void;
}

const labels: Record<Environment, string> = {
  paper: "Paper",
  testnet: "Testnet",
  live: "LIVE",
};

export function EnvironmentSelector({
  runtime,
  busy,
  onChange,
}: EnvironmentSelectorProps) {
  const active = runtime?.active_engine_environment ?? null;
  const switching = runtime?.transition_state === "switching";
  const blocked = busy || switching || runtime === null;
  const statusLabel = runtime === null
    ? "بيئة المحرك غير متاحة"
    : runtime.transition_state === "switching"
      ? `Switching to ${labels[runtime.requested_environment]}…`
      : runtime.transition_state === "restart_required"
        ? "Restart required"
        : runtime.transition_state === "failed"
          ? "Environment switch failed"
          : runtime.transition_state === "mismatch"
            ? "Environment mismatch"
            : active === "live"
              ? "LIVE — REAL FUNDS"
              : active
                ? labels[active]
                : "بيئة المحرك غير متاحة";
  const statusTone = runtime?.transition_state === "ready"
    ? active === "live"
      ? "negative"
      : active === "testnet"
        ? "warning"
        : "info"
    : runtime?.transition_state === "switching"
      ? "warning"
      : "negative";

  return (
    <div className="environment-selector" aria-label="Active trading environment">
      <StatusPill
        label={statusLabel}
        tone={statusTone}
        pulse={switching || active === "live"}
      />
      <div className="environment-selector-buttons" role="group" aria-label="Switch trading environment">
        {(["paper", "testnet", "live"] as const).map((environment) => (
          <button
            className={[
              "environment-option",
              active === environment ? "active" : "",
              environment === "live" ? "live-option" : "",
            ].filter(Boolean).join(" ")}
            disabled={blocked || (active === environment && runtime?.activated === true)}
            key={environment}
            type="button"
            onClick={() => onChange(environment)}
          >
            {environment === "live" && <Icon name="alert" size={14} />}
            {labels[environment]}
          </button>
        ))}
      </div>
      {runtime && runtime.transition_state !== "ready" && (
        <span className="environment-status-message" role="status">
          {runtime.message_ar
            ?? `المحفوظ: ${labels[runtime.configured_environment]} · الفعلي: ${labels[runtime.active_engine_environment]}`}
        </span>
      )}
    </div>
  );
}
