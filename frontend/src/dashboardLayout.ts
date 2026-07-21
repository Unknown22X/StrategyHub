import type { JsonValue } from "./types";

export const dashboardWidgetLabels = {
  summary: "ملخص الحساب",
  active: "الاستراتيجية والمركز",
  strategiesRisk: "الاستراتيجيات والمخاطر",
  marketAlerts: "السوق والتنبيهات",
  orders: "الأوامر المفتوحة",
  performance: "الأداء والنتائج",
  activity: "النشاط الأخير",
} as const;

export type DashboardWidgetId = keyof typeof dashboardWidgetLabels;
export type DashboardDensity = "compact" | "comfortable";

export interface DashboardLayoutSettings {
  order: DashboardWidgetId[];
  hidden: DashboardWidgetId[];
  density: DashboardDensity;
}

export const defaultDashboardLayout: DashboardLayoutSettings = {
  order: [
    "summary",
    "active",
    "strategiesRisk",
    "marketAlerts",
    "orders",
    "performance",
    "activity",
  ],
  hidden: [],
  density: "compact",
};

export function normalizeDashboardLayout(
  value: Record<string, JsonValue> | null | undefined,
): DashboardLayoutSettings {
  const allIds = Object.keys(dashboardWidgetLabels) as DashboardWidgetId[];
  const orderValue = Array.isArray(value?.order)
    ? value.order.filter(isDashboardWidgetId)
    : [];
  const uniqueOrder = Array.from(new Set(orderValue));
  const missing = allIds.filter((id) => !uniqueOrder.includes(id));
  const hidden = Array.isArray(value?.hidden)
    ? Array.from(new Set(value.hidden.filter(isDashboardWidgetId)))
    : [];
  const density = value?.density === "comfortable" ? "comfortable" : "compact";
  return {
    order: [...uniqueOrder, ...missing],
    hidden,
    density,
  };
}

export function serializeDashboardLayout(
  layout: DashboardLayoutSettings,
): Record<string, JsonValue> {
  return {
    order: layout.order,
    hidden: layout.hidden,
    density: layout.density,
  };
}

function isDashboardWidgetId(value: JsonValue): value is DashboardWidgetId {
  return typeof value === "string" && value in dashboardWidgetLabels;
}
