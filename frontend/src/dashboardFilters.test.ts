import { describe, expect, it } from "vitest";

import {
  defaultDashboardFilters,
  normalizeDashboardFilters,
  serializeDashboardFilters,
} from "./dashboardFilters";


describe("dashboard filters", () => {
  it("normalizes persisted display filters without changing trading state", () => {
    expect(normalizeDashboardFilters({
      environment: "testnet",
      strategy_id: "strategy-1",
      symbol: "BTC_USDT",
      period: "30d",
      event_type: "decision",
    })).toEqual({
      environment: "testnet",
      strategyId: "strategy-1",
      symbol: "BTC_USDT",
      period: "30d",
      eventType: "decision",
    });
  });

  it("falls back safely for malformed settings", () => {
    expect(normalizeDashboardFilters({
      environment: "production",
      strategy_id: 4,
      period: "quarter",
      event_type: "orders",
    })).toEqual(defaultDashboardFilters);
  });

  it("serializes backend-safe keys", () => {
    expect(serializeDashboardFilters(defaultDashboardFilters)).toEqual({
      environment: "current",
      strategy_id: null,
      symbol: null,
      period: "today",
      event_type: "all",
    });
  });
});
