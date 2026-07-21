import { useCallback, useEffect, useRef, useState } from "react";

import { loadDashboard } from "../api";
import type { DashboardBundle, EngineEvent } from "../types";

const loadingBundle: DashboardBundle = {
  runtime: { status: "loading" },
  settings: { status: "loading" },
  strategyTypes: { status: "loading" },
  strategies: { status: "loading" },
  strategyOverview: { status: "loading" },
  liveState: { status: "loading" },
  testnetState: { status: "loading" },
  liveRisk: { status: "loading" },
  testnetRisk: { status: "loading" },
  privateStream: { status: "loading" },
  paperAccount: { status: "loading" },
  paperPerformance: { status: "loading" },
  paperRisk: { status: "loading" },
  paperPosition: { status: "loading" },
  paperPendingEntry: { status: "loading" },
  watchlist: { status: "loading" },
  activity: { status: "loading" },
  loadedAt: "",
};

function isEngineEvent(value: unknown): value is EngineEvent {
  if (typeof value !== "object" || value === null) return false;
  const event = value as Partial<EngineEvent>;
  return typeof event.event_id === "string"
    && typeof event.sequence === "number"
    && typeof event.category === "string"
    && typeof event.action === "string"
    && typeof event.resource === "string"
    && typeof event.occurred_at === "string";
}

export function useDashboard(refreshIntervalMs = 5000) {
  const [bundle, setBundle] = useState<DashboardBundle>(loadingBundle);
  const [refreshing, setRefreshing] = useState(false);
  const [eventStreamConnected, setEventStreamConnected] = useState(false);
  const activeRequest = useRef<AbortController | null>(null);
  const eventRefreshTimer = useRef<number | null>(null);

  const refresh = useCallback(async () => {
    activeRequest.current?.abort();
    const controller = new AbortController();
    activeRequest.current = controller;
    setRefreshing(true);
    try {
      const next = await loadDashboard(controller.signal);
      if (!controller.signal.aborted) {
        setBundle(next);
      }
    } catch (error) {
      if (!(error instanceof DOMException && error.name === "AbortError")) {
        setBundle((current) => ({
          ...current,
          runtime: {
            status: "error",
            message: error instanceof Error ? error.message : "تعذر الاتصال بالمحرك.",
          },
          loadedAt: new Date().toISOString(),
        }));
      }
    } finally {
      if (!controller.signal.aborted) {
        setRefreshing(false);
      }
    }
  }, []);

  useEffect(() => {
    void refresh();
    const pollingInterval = eventStreamConnected
      ? Math.max(refreshIntervalMs, 30_000)
      : refreshIntervalMs;
    const interval = window.setInterval(() => void refresh(), pollingInterval);
    return () => {
      window.clearInterval(interval);
      activeRequest.current?.abort();
    };
  }, [eventStreamConnected, refresh, refreshIntervalMs]);

  useEffect(() => {
    if (typeof WebSocket === "undefined") return undefined;

    let disposed = false;
    let retryCount = 0;
    let reconnectTimer: number | null = null;
    let socket: WebSocket | null = null;

    const scheduleRefresh = () => {
      if (eventRefreshTimer.current !== null) {
        window.clearTimeout(eventRefreshTimer.current);
      }
      eventRefreshTimer.current = window.setTimeout(() => {
        eventRefreshTimer.current = null;
        void refresh();
      }, 150);
    };

    const connect = () => {
      if (disposed) return;
      const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
      socket = new WebSocket(`${protocol}//${window.location.host}/v1/events`);

      socket.onopen = () => {
        retryCount = 0;
        setEventStreamConnected(true);
        // Always restore an authoritative REST snapshot after a reconnect.
        void refresh();
      };
      socket.onmessage = (message) => {
        try {
          const event: unknown = JSON.parse(String(message.data));
          if (isEngineEvent(event)) scheduleRefresh();
        } catch {
          // Ignore malformed or non-JSON messages; polling remains the fallback.
        }
      };
      socket.onerror = () => socket?.close();
      socket.onclose = () => {
        setEventStreamConnected(false);
        if (disposed) return;
        const delay = Math.min(1000 * 2 ** retryCount, 15_000);
        retryCount += 1;
        reconnectTimer = window.setTimeout(connect, delay);
      };
    };

    connect();
    return () => {
      disposed = true;
      setEventStreamConnected(false);
      if (reconnectTimer !== null) window.clearTimeout(reconnectTimer);
      if (eventRefreshTimer.current !== null) {
        window.clearTimeout(eventRefreshTimer.current);
        eventRefreshTimer.current = null;
      }
      socket?.close();
    };
  }, [refresh]);

  return { bundle, refresh, refreshing, eventStreamConnected };
}
