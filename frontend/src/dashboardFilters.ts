import type { Environment, JsonValue } from "./types";

export type DashboardPeriod = "today" | "7d" | "30d" | "all";
export type DashboardEventType =
  | "all"
  | "decision"
  | "strategy"
  | "order"
  | "paper"
  | "risk"
  | "system"
  | "research";

export interface DashboardFilters {
  environment: Environment | "current";
  strategyId: string | null;
  symbol: string | null;
  period: DashboardPeriod;
  eventType: DashboardEventType;
}

export const defaultDashboardFilters: DashboardFilters = {
  environment: "current",
  strategyId: null,
  symbol: null,
  period: "today",
  eventType: "all",
};

export function normalizeDashboardFilters(
  value: Record<string, JsonValue> | null | undefined,
): DashboardFilters {
  return {
    environment: isEnvironmentFilter(value?.environment)
      ? value.environment
      : "current",
    strategyId: optionalString(value?.strategy_id),
    symbol: optionalString(value?.symbol),
    period: isPeriod(value?.period) ? value.period : "today",
    eventType: isEventType(value?.event_type) ? value.event_type : "all",
  };
}

export function serializeDashboardFilters(
  filters: DashboardFilters,
): Record<string, JsonValue> {
  return {
    environment: filters.environment,
    strategy_id: filters.strategyId,
    symbol: filters.symbol,
    period: filters.period,
    event_type: filters.eventType,
  };
}

function optionalString(value: JsonValue | undefined): string | null {
  return typeof value === "string" && value.trim() ? value : null;
}

function isEnvironmentFilter(
  value: JsonValue | undefined,
): value is Environment | "current" {
  return value === "current" || value === "live" || value === "testnet" || value === "paper";
}

function isPeriod(value: JsonValue | undefined): value is DashboardPeriod {
  return value === "today" || value === "7d" || value === "30d" || value === "all";
}

function isEventType(value: JsonValue | undefined): value is DashboardEventType {
  return value === "all"
    || value === "decision"
    || value === "strategy"
    || value === "order"
    || value === "paper"
    || value === "risk"
    || value === "system"
    || value === "research";
}
