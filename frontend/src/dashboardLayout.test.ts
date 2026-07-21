import { describe, expect, it } from "vitest";

import {
  defaultDashboardLayout,
  normalizeDashboardLayout,
  serializeDashboardLayout,
} from "./dashboardLayout";


describe("dashboard layout", () => {
  it("normalizes persisted order, hidden widgets, and density", () => {
    const layout = normalizeDashboardLayout({
      order: ["orders", "summary", "orders", "unknown"],
      hidden: ["activity", "unknown"],
      density: "comfortable",
    });

    expect(layout.order.slice(0, 2)).toEqual(["orders", "summary"]);
    expect(layout.order).toHaveLength(defaultDashboardLayout.order.length);
    expect(layout.hidden).toEqual(["activity"]);
    expect(layout.density).toBe("comfortable");
  });

  it("falls back safely when stored settings are malformed", () => {
    expect(normalizeDashboardLayout({ order: "bad", hidden: null })).toEqual(
      defaultDashboardLayout,
    );
  });

  it("serializes only backend-safe JSON values", () => {
    expect(serializeDashboardLayout(defaultDashboardLayout)).toEqual({
      order: defaultDashboardLayout.order,
      hidden: [],
      density: "compact",
    });
  });
});
