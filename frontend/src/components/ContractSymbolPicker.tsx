import { useEffect, useId, useMemo, useState } from "react";

import { loadGateContracts, loadMarketSnapshot } from "../api";
import { formatDateTime, formatMoney } from "../lib/format";
import type { Environment, MarketDataSnapshot, PublicContract } from "../types";
import { Icon } from "./Icon";
import { StatusPill } from "./StateView";

interface ContractSymbolPickerProps {
  value: string;
  onChange: (value: string) => void;
  environment: Environment;
  label?: string;
  disabled?: boolean;
  required?: boolean;
  help?: string;
}

export function ContractSymbolPicker({
  value,
  onChange,
  environment,
  label = "Coin / contract",
  disabled = false,
  required = false,
  help = "Search Gate.io USDT perpetual contracts. Manual symbols remain available and are validated by the engine on save.",
}: ContractSymbolPickerProps) {
  const listId = useId();
  const [contracts, setContracts] = useState<PublicContract[]>([]);
  const [loading, setLoading] = useState(false);
  const [catalogError, setCatalogError] = useState<string | null>(null);
  const [snapshot, setSnapshot] = useState<MarketDataSnapshot | null>(null);
  const normalized = value.trim().toUpperCase();
  const exact = useMemo(
    () => contracts.some((contract) => contract.symbol === normalized),
    [contracts, normalized],
  );

  useEffect(() => {
    const controller = new AbortController();
    const timer = window.setTimeout(() => {
      setLoading(true);
      loadGateContracts(normalized, controller.signal)
        .then((items) => {
          setContracts(items.slice(0, 80));
          setCatalogError(null);
        })
        .catch((error: unknown) => {
          if (controller.signal.aborted) return;
          setCatalogError(error instanceof Error ? error.message : "Contract catalog unavailable.");
        })
        .finally(() => {
          if (!controller.signal.aborted) setLoading(false);
        });
    }, 120);
    return () => {
      window.clearTimeout(timer);
      controller.abort();
    };
  }, [normalized]);

  useEffect(() => {
    if (!normalized) {
      setSnapshot(null);
      return;
    }
    let active = true;
    let controller = new AbortController();
    const refresh = () => {
      controller.abort();
      controller = new AbortController();
      loadMarketSnapshot(normalized, controller.signal)
        .then((next) => {
          if (active) setSnapshot(next);
        })
        .catch(() => {
          if (active) setSnapshot(null);
        });
    };
    refresh();
    const interval = window.setInterval(refresh, 5000);
    return () => {
      active = false;
      controller.abort();
      window.clearInterval(interval);
    };
  }, [normalized]);

  return (
    <label className="field contract-symbol-picker">
      <span>{label}</span>
      <div className="contract-picker-input-wrap">
        <input
          dir="ltr"
          list={listId}
          value={value}
          disabled={disabled}
          required={required}
          placeholder="BTC_USDT"
          autoComplete="off"
          onChange={(event) => onChange(event.target.value.toUpperCase())}
        />
        {loading && <Icon name="refresh" />}
      </div>
      <datalist id={listId}>
        {contracts.map((contract) => (
          <option key={contract.symbol} value={contract.symbol}>
            Min Quantity {contract.minimum_quantity} · Step {contract.quantity_step}
          </option>
        ))}
      </datalist>
      <small>{help}</small>
      <div className="contract-picker-status" aria-live="polite">
        <StatusPill
          label={exact ? "Gate contract selected" : normalized ? "Manual symbol — validation pending" : "Choose a contract"}
          tone={exact ? "positive" : normalized ? "warning" : "neutral"}
        />
        <StatusPill label={`${environment.toUpperCase()} · Gate public market`} tone={environment === "live" ? "warning" : "info"} />
        {snapshot && (
          <>
            <StatusPill label={`${formatMoney(snapshot.last_price)} · ${snapshot.state}`} tone={snapshot.state === "fresh" ? "positive" : "warning"} />
            <small>{snapshot.source} · {formatDateTime(snapshot.observed_at)}</small>
          </>
        )}
      </div>
      {catalogError && <small className="warning-text">Options unavailable: {catalogError}. Manual entry still works.</small>}
    </label>
  );
}
