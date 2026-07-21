import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  cancelPaperPendingEntry,
  createBackup,
  createStrategy,
  createStrategyFromBacktest,
  deleteBackup,
  deleteStrategy,
  duplicateStrategy,
  exportSupportLogs,
  listBackups,
  listBacktests,
  listDiscoveryScans,
  loadAccountPerformance,
  loadAccountRiskPolicy,
  loadBacktestEquity,
  loadBacktestTrades,
  loadCredentialStatus,
  loadDashboard,
  loadMarketCandles,
  loadMarketSnapshot,
  loadReconciliationReadiness,
  loadTradeHistory,
  loadTradeHistorySummary,
  previewManualOrder,
  removeCredentials,
  requestReconciliation,
  restoreBackup,
  runBacktest,
  runDiscoveryScan,
  saveAccountRiskPolicy,
  saveApplicationSettings,
  saveCredentials,
  submitManualOrder,
  switchRuntimeEnvironment,
  testCredentials,
  updateStrategy,
} from "./api";
import type {
  ApplicationSettings,
  ManualOrderPreview,
  ManualOrderRequest,
  StrategyInstanceCreate,
} from "./types";

const fetchMock = vi.fn();

beforeEach(() => {
  fetchMock.mockReset();
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("dashboard API boundary", () => {
  it("keeps partial failures explicit and treats a missing paper position as empty", async () => {
    fetchMock.mockImplementation((input: RequestInfo | URL) => {
      const path = String(input);
      const responses: Record<string, Response> = {
        "/health": jsonResponse({
          lifecycle: "running",
          started_at: "2026-07-16T20:00:00Z",
          last_heartbeat_at: "2026-07-16T20:01:00Z",
          state_revision: 2,
        }),
        "/v1/settings": jsonResponse({ detail: "settings unavailable" }, 503),
        "/v1/strategy-types": jsonResponse([]),
        "/v1/strategies": jsonResponse([]),
        "/v1/strategies/overview": jsonResponse([]),
        "/v1/exchange/live/state": jsonResponse(modeState("live")),
        "/v1/exchange/testnet/state": jsonResponse(modeState("testnet")),
        "/v1/account-risk/live": jsonResponse(accountRisk("live")),
        "/v1/account-risk/testnet": jsonResponse(accountRisk("testnet")),
        "/v1/exchange/private-stream": jsonResponse({
          mode: "live",
          status: "reconnecting",
          connected: false,
          subscribed_channels: [],
          last_event_at: null,
          last_reconciled_at: null,
          last_error: "heartbeat_timeout",
          revision: 3,
        }),
        "/v1/paper-account": jsonResponse({
          mode: "paper",
          starting_balance: "1000",
          available_futures_balance: "1000",
          realized_pnl_total: "0",
          fees_total: "0",
          funding_total: "0",
          net_pnl_total: "0",
          position_quantity: "0",
          pending_entry: false,
          protection_state: "none",
          cooldown_until: null,
          risk_state: "ready",
          last_change_reason: "initialized",
          revision: 1,
        }),
        "/v1/performance/account/paper?period=all&maximum_points=2": jsonResponse({
          mode: "paper",
          period: "all",
          generated_at: "2026-07-16T20:01:00Z",
          points: [
            {
              point_id: 1,
              mode: "paper",
              occurred_at: "2026-07-16T20:00:00Z",
              total_equity: "1000",
              available_balance: "1000",
              used_margin: "0",
              margin_usage_percentage: "0",
              realized_pnl_total: "0",
              unrealized_pnl: "0",
              fees_total: "0",
              funding_total: "0",
              net_pnl_total: "0",
              open_exposure: "0",
            },
          ],
          baseline_equity: "1000",
          ending_equity: "1000",
          equity_change: "0",
          equity_change_percentage: "0",
          maximum_drawdown_percentage: "0",
          realized_pnl_total: "0",
          unrealized_pnl: "0",
          fees_total: "0",
          funding_total: "0",
          net_pnl_total: "0",
          open_exposure: "0",
        }),
        "/v1/paper/risk": jsonResponse({
          day: "2026-07-16",
          baseline_balance: "1000",
          realized_net_loss: "0",
          losing_trades: 0,
          automatic_fills: 0,
          settings: {
            daily_loss_limit: "100",
            losing_trade_limit: 3,
            automatic_fill_limit: 10,
            cooldown_seconds: 60,
          },
          manual_entries_blocked: false,
          automatic_entries_blocked: false,
          cooldown_until: null,
        }),
        "/v1/paper/position": jsonResponse({ detail: "No paper position" }, 404),
        "/v1/paper/pending-entry-state": jsonResponse(null),
        "/v1/paper/watchlist": jsonResponse({ items: [], automatic_trading_enabled: false }),
        "/v1/activity?limit=200": jsonResponse([
          {
            event_id: "runtime:1",
            occurred_at: "2026-07-16T08:00:00Z",
            category: "system",
            severity: "positive",
            title_ar: "حالة محرك RangeBot",
            detail_ar: "المحرك في حالة running",
            environment: null,
            symbol: null,
            strategy_instance_id: null,
            strategy_name: null,
            status: "running",
            source_identity: "1",
          },
        ]),
      };
      return Promise.resolve(responses[path] ?? jsonResponse({ detail: "not found" }, 404));
    });

    const bundle = await loadDashboard();

    expect(bundle.runtime.status).toBe("ready");
    expect(bundle.settings).toEqual({ status: "error", message: "settings unavailable" });
    expect(bundle.strategyOverview).toEqual({ status: "ready", data: [] });
    expect(bundle.liveRisk).toEqual({
      status: "ready",
      data: expect.objectContaining({ environment: "live", remaining_loss_allowance: "100" }),
    });
    expect(bundle.testnetRisk).toEqual({
      status: "ready",
      data: expect.objectContaining({ environment: "testnet", automatic_trades: 0 }),
    });
    expect(bundle.privateStream).toEqual({
      status: "ready",
      data: expect.objectContaining({ status: "reconnecting", connected: false }),
    });
    expect(bundle.paperPerformance).toEqual({
      status: "ready",
      data: expect.objectContaining({ mode: "paper", ending_equity: "1000" }),
    });
    expect(bundle.paperPosition).toEqual({ status: "ready", data: null });
    expect(bundle.paperPendingEntry).toEqual({ status: "ready", data: null });
    expect(bundle.activity).toEqual({
      status: "ready",
      data: [expect.objectContaining({ category: "system", status: "running" })],
    });
  });

  it("loads and commits account-wide risk policy through localhost", async () => {
    const policy = {
      daily_loss_limit: "125",
      losing_trade_limit: 4,
      automatic_trade_limit: 6,
      revision: 2,
      updated_at: "2026-07-16T20:00:00Z",
    };
    fetchMock
      .mockResolvedValueOnce(jsonResponse(policy))
      .mockResolvedValueOnce(jsonResponse(policy));

    const loaded = await loadAccountRiskPolicy();
    const saved = await saveAccountRiskPolicy({
      daily_loss_limit: "125",
      losing_trade_limit: 4,
      automatic_trade_limit: 6,
    });

    expect(loaded.revision).toBe(2);
    expect(saved.automatic_trade_limit).toBe(6);
    expect(fetchMock).toHaveBeenNthCalledWith(
      1,
      "/v1/account-risk/policy",
      expect.objectContaining({
        headers: { Accept: "application/json" },
      }),
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      2,
      "/v1/account-risk/policy",
      expect.objectContaining({
        method: "PUT",
        body: JSON.stringify({
          daily_loss_limit: "125",
          losing_trade_limit: 4,
          automatic_trade_limit: 6,
        }),
      }),
    );
  });

  it("persists application settings through the engine endpoint", async () => {
    const settings: Omit<ApplicationSettings, "revision" | "updated_at"> = {
      environment: "paper",
      ui_language: "ar",
      dashboard_layout: {},
      dashboard_filters: {},
      sidebar_preferences: { collapsed: true },
      application_preferences: {},
    };
    fetchMock.mockResolvedValue(jsonResponse({ ...settings, revision: 1, updated_at: null }));

    await saveApplicationSettings(settings);

    expect(fetchMock).toHaveBeenCalledWith(
      "/v1/settings",
      expect.objectContaining({ method: "PUT", body: JSON.stringify(settings) }),
    );
  });

  it("switches the authoritative runtime environment through the dedicated endpoint", async () => {
    const runtime = {
      configured_environment: "testnet",
      requested_environment: "testnet",
      active_engine_environment: "testnet",
      exchange_adapter_environment: "testnet",
      public_rest_environment: "testnet",
      public_websocket_environment: "testnet",
      private_websocket_environment: "testnet",
      credential_profile: "testnet",
      transition_state: "ready",
      restart_required: false,
      activated: true,
      transition_started_at: null,
      transition_completed_at: "2026-07-21T06:00:00Z",
      failure_code: null,
      message_ar: null,
      revision: 2,
    };
    fetchMock.mockResolvedValue(jsonResponse(runtime));

    const result = await switchRuntimeEnvironment("testnet");

    expect(result.active_engine_environment).toBe("testnet");
    expect(fetchMock).toHaveBeenCalledWith(
      "/v1/runtime/environment/switch",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ environment: "testnet", confirmation: "" }),
      }),
    );
  });

  it("loads structured reconciliation readiness and requests a bounded refresh", async () => {
    const readiness = {
      mode: "testnet",
      state: "refreshing",
      ready: false,
      refresh_in_progress: true,
      snapshot_age_seconds: null,
      maximum_snapshot_age_seconds: 30,
      last_attempt_at: "2026-07-21T08:00:00Z",
      last_success_at: null,
      attempt_count: 1,
      failure_code: null,
      message_ar: null,
      reason_codes: [
        "reconciliation_snapshot_missing",
        "reconciliation_refreshing",
        "reconciliation_not_ready",
      ],
      snapshot: null,
    };
    fetchMock
      .mockResolvedValueOnce(jsonResponse(readiness))
      .mockResolvedValueOnce(jsonResponse(modeState("testnet")));

    const loaded = await loadReconciliationReadiness("testnet");
    const refreshed = await requestReconciliation("testnet");

    expect(loaded.reason_codes).toContain("reconciliation_refreshing");
    expect(refreshed.mode).toBe("testnet");
    expect(fetchMock).toHaveBeenNthCalledWith(
      1,
      "/v1/exchange/testnet/reconciliation",
      expect.any(Object),
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      2,
      "/v1/exchange/testnet/reconcile",
      expect.objectContaining({ method: "POST" }),
    );
  });

  it("surfaces the structured environment-switch failure message", async () => {
    fetchMock.mockResolvedValue(jsonResponse({
      configured_environment: "live",
      requested_environment: "testnet",
      active_engine_environment: "live",
      exchange_adapter_environment: "live",
      public_rest_environment: "live",
      public_websocket_environment: "live",
      private_websocket_environment: "live",
      credential_profile: "live",
      transition_state: "restart_required",
      restart_required: true,
      activated: false,
      transition_started_at: "2026-07-21T06:00:00Z",
      transition_completed_at: null,
      failure_code: "restart_required",
      message_ar: "يلزم إعادة تشغيل محرك RangeBot بالبيئة المطلوبة.",
      revision: 3,
    }, 409));

    await expect(switchRuntimeEnvironment("testnet")).rejects.toMatchObject({
      code: "restart_required",
      message: "يلزم إعادة تشغيل محرك RangeBot بالبيئة المطلوبة.",
    });
  });

  it("creates strategy instances using the registry-backed API", async () => {
    const request: StrategyInstanceCreate = {
      type_id: "range",
      name: "نطاق BTC",
      environment: "paper",
      symbol: "BTC_USDT",
      timeframe_minutes: 5,
      direction: "both",
      requested_margin: "20",
      requested_leverage: 3,
      configuration: { lookback_candles: 20 },
    };
    fetchMock.mockResolvedValue(jsonResponse({
      ...request,
      instance_id: "strategy-1",
      status: "stopped",
      created_at: "2026-07-16T20:00:00Z",
      updated_at: "2026-07-16T20:00:00Z",
      revision: 1,
    }));

    const created = await createStrategy(request);

    expect(created.instance_id).toBe("strategy-1");
    expect(fetchMock).toHaveBeenCalledWith(
      "/v1/strategies",
      expect.objectContaining({ method: "POST", body: JSON.stringify(request) }),
    );
  });

  it("routes strategy editing, duplication, and deletion through the engine", async () => {
    fetchMock
      .mockResolvedValueOnce(jsonResponse({ instance_id: "strategy-1", name: "Renamed" }))
      .mockResolvedValueOnce(jsonResponse({ instance_id: "strategy-copy", name: "Copy" }, 201))
      .mockResolvedValueOnce(new Response(null, { status: 204 }));

    await updateStrategy("strategy-1", { name: "Renamed" });
    await duplicateStrategy("strategy-1", "Copy");
    await deleteStrategy("strategy-1");

    expect(fetchMock).toHaveBeenNthCalledWith(
      1,
      "/v1/strategies/strategy-1",
      expect.objectContaining({ method: "PUT", body: JSON.stringify({ name: "Renamed" }) }),
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      2,
      "/v1/strategies/strategy-1/duplicate",
      expect.objectContaining({ method: "POST", body: JSON.stringify({ name: "Copy" }) }),
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      3,
      "/v1/strategies/strategy-1",
      expect.objectContaining({ method: "DELETE" }),
    );
  });

  it("keeps credential operations inside protected engine endpoints", async () => {
    const keyValue = ["account", "key"].join("-");
    const secretValue = ["account", "credential"].join("-");
    fetchMock
      .mockResolvedValueOnce(jsonResponse({ mode: "live", configured: false }))
      .mockResolvedValueOnce(jsonResponse({ mode: "live", configured: true }))
      .mockResolvedValueOnce(jsonResponse({ mode: "live", valid: true, message_ar: "صالحة" }))
      .mockResolvedValueOnce(jsonResponse({ mode: "live", configured: false }));

    await loadCredentialStatus("live");
    await saveCredentials("live", keyValue, secretValue);
    await testCredentials("live");
    await removeCredentials("live");

    expect(fetchMock).toHaveBeenNthCalledWith(1, "/v1/exchange/live/credentials", expect.any(Object));
    expect(fetchMock).toHaveBeenNthCalledWith(
      2,
      "/v1/exchange/credentials",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ mode: "live", api_key: keyValue, api_secret: secretValue }),
      }),
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      3,
      "/v1/exchange/live/credentials/test",
      expect.objectContaining({ method: "POST" }),
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      4,
      "/v1/exchange/live/credentials",
      expect.objectContaining({ method: "DELETE" }),
    );
  });

  it("loads strategy chart data only from RangeBot market-data endpoints", async () => {
    fetchMock
      .mockResolvedValueOnce(jsonResponse({ symbol: "BTC_USDT", timeframe_minutes: 15, candles: [], source: "gate_rest", updated_at: "2026-07-17T00:00:00Z" }))
      .mockResolvedValueOnce(jsonResponse({ symbol: "BTC_USDT", last_price: "65000", mark_price: "64990", state: "fresh" }));

    await loadMarketCandles("BTC_USDT", 15);
    await loadMarketSnapshot("BTC_USDT");

    expect(fetchMock).toHaveBeenNthCalledWith(
      1,
      "/v1/market-data/BTC_USDT/candles/15",
      expect.any(Object),
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      2,
      "/v1/market-data/BTC_USDT",
      expect.any(Object),
    );
  });

  it("routes discovery, backtesting, and stopped application through localhost research endpoints", async () => {
    const scanRequest = {
      strategy_type_id: "range",
      timeframe_minutes: 15,
      configuration: { timeframe_minutes: 15 },
      minimum_quote_volume: "1000000",
      maximum_symbols: 30,
      maximum_candidates: 15,
      minimum_score: 35,
    };
    const backtestRequest = {
      scan_id: "scan-1",
      strategy_type_id: "range",
      symbol: "BTC_USDT",
      timeframe_minutes: 15,
      configuration: { timeframe_minutes: 15 },
      start: "2026-01-01T00:00:00Z",
      end: "2026-04-01T00:00:00Z",
      settings: {
        initial_balance: "1000",
        margin_per_trade: "100",
        leverage: 3,
        taker_fee_rate: "0.0005",
        slippage_basis_points: "5",
        default_take_profit_percentage: "5",
        default_stop_loss_percentage: "3",
        minimum_trades_for_assessment: 20,
      },
    };
    const createRequest = {
      name: "BTC Range Research",
      environment: "paper" as const,
      direction: "both" as const,
    };
    fetchMock
      .mockResolvedValueOnce(jsonResponse({ scan_id: "scan-1", request: scanRequest, result: { candidates: [] } }))
      .mockResolvedValueOnce(jsonResponse({ backtest_id: "backtest-1", request: backtestRequest, result: { trades: [], equity_curve: [] } }))
      .mockResolvedValueOnce(jsonResponse([{ trade_number: 1 }]))
      .mockResolvedValueOnce(jsonResponse([{ occurred_at: "2026-01-01T00:00:00Z", equity: "1000", drawdown_percentage: "0" }]))
      .mockResolvedValueOnce(jsonResponse({ instance_id: "strategy-from-backtest", status: "stopped" }))
      .mockResolvedValueOnce(jsonResponse([{ scan_id: "scan-1" }]))
      .mockResolvedValueOnce(jsonResponse([{ backtest_id: "backtest-1" }]));

    await runDiscoveryScan(scanRequest);
    await runBacktest(backtestRequest);
    await loadBacktestTrades("backtest-1");
    await loadBacktestEquity("backtest-1");
    await createStrategyFromBacktest("backtest-1", createRequest);
    await listDiscoveryScans();
    await listBacktests();

    expect(fetchMock).toHaveBeenNthCalledWith(
      1,
      "/v1/discovery/scans",
      expect.objectContaining({ method: "POST", body: JSON.stringify(scanRequest) }),
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      2,
      "/v1/backtests",
      expect.objectContaining({ method: "POST", body: JSON.stringify(backtestRequest) }),
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      3,
      "/v1/backtests/backtest-1/trades",
      expect.any(Object),
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      4,
      "/v1/backtests/backtest-1/equity",
      expect.any(Object),
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      5,
      "/v1/backtests/backtest-1/create-strategy",
      expect.objectContaining({ method: "POST", body: JSON.stringify(createRequest) }),
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      6,
      "/v1/discovery/scans",
      expect.any(Object),
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      7,
      "/v1/backtests",
      expect.any(Object),
    );
  });

  it("cancels Paper pending entries through the engine", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ pending_entry: false }));

    await cancelPaperPendingEntry();

    expect(fetchMock).toHaveBeenCalledWith(
      "/v1/paper/pending-entry",
      expect.objectContaining({ method: "DELETE" }),
    );
  });

  it("routes manual preview and submission only through RangeBot", async () => {
    const request: ManualOrderRequest = {
      environment: "testnet",
      symbol: "BTC_USDT",
      direction: "long",
      order_type: "market",
      size_mode: "margin",
      margin_amount: "100",
      leverage: 5,
      time_in_force: "ioc",
    };
    const preview = manualPreview(request);
    fetchMock
      .mockResolvedValueOnce(jsonResponse(preview))
      .mockResolvedValueOnce(jsonResponse({
        accepted: true,
        environment: "testnet",
        origin: "manual",
        client_request_id: "request-1",
        order_id: "order-1",
        message_ar: "تم قبول الأمر",
        preview,
      }));

    const loadedPreview = await previewManualOrder(request);
    await submitManualOrder(loadedPreview);

    expect(fetchMock).toHaveBeenNthCalledWith(
      1,
      "/v1/manual-orders/preview",
      expect.objectContaining({ method: "POST", body: JSON.stringify(request) }),
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      2,
      "/v1/manual-orders",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({
          request,
          preview_fingerprint: preview.safety_fingerprint,
        }),
      }),
    );
  });

  it("routes backup and support operations through the localhost engine", async () => {
    const backup = {
      name: "rangebot-manual-20260717.db",
      kind: "manual" as const,
      created_at: "2026-07-17T01:00:00Z",
      size_bytes: 4096,
    };
    fetchMock
      .mockResolvedValueOnce(jsonResponse([backup]))
      .mockResolvedValueOnce(jsonResponse(backup))
      .mockResolvedValueOnce(jsonResponse({
        name: backup.name,
        deleted: true,
        message_ar: "تم الحذف",
      }))
      .mockResolvedValueOnce(jsonResponse({
        restored: backup,
        safety_backup: { ...backup, name: "rangebot-pre-restore-safe.db", kind: "pre_restore" },
        reconciled_mode: "live",
        reconciliation_succeeded: true,
        emergency_stop_active: true,
        message_ar: "تمت الاستعادة",
      }))
      .mockResolvedValueOnce(new Response(new Uint8Array([115, 117, 112, 112, 111, 114, 116]), {
        status: 200,
        headers: {
          "Content-Type": "application/zip",
          "Content-Disposition": 'attachment; filename="rangebot-support.zip"',
        },
      }));

    await listBackups();
    await createBackup();
    await deleteBackup(backup.name);
    await restoreBackup(backup.name);
    const archive = await exportSupportLogs();

    expect(archive.filename).toBe("rangebot-support.zip");
    expect(fetchMock).toHaveBeenNthCalledWith(
      4,
      `/v1/backups/${backup.name}/restore`,
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ confirmation: "RESTORE RANGEBOT" }),
      }),
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      5,
      "/v1/logs/export",
      { method: "POST" },
    );
  });

  it("loads the engine-owned account performance series", async () => {
    fetchMock.mockResolvedValue(jsonResponse({
      mode: "live",
      period: "7d",
      generated_at: "2026-07-17T10:00:00Z",
      points: [],
      baseline_equity: null,
      ending_equity: null,
      equity_change: null,
      equity_change_percentage: null,
      maximum_drawdown_percentage: null,
      realized_pnl_total: null,
      unrealized_pnl: null,
      fees_total: null,
      funding_total: null,
      net_pnl_total: null,
      open_exposure: null,
    }));

    const result = await loadAccountPerformance("live", "7d");

    expect(result.period).toBe("7d");
    expect(fetchMock).toHaveBeenCalledWith(
      "/v1/performance/account/live?period=7d&maximum_points=1000",
      { headers: { Accept: "application/json" }, signal: undefined },
    );
  });

  it("loads the Paper performance ledger through the same endpoint", async () => {
    fetchMock.mockResolvedValue(jsonResponse({
      mode: "paper",
      period: "all",
      generated_at: "2026-07-17T10:00:00Z",
      points: [],
      baseline_equity: null,
      ending_equity: null,
      equity_change: null,
      equity_change_percentage: null,
      maximum_drawdown_percentage: null,
      realized_pnl_total: null,
      unrealized_pnl: null,
      fees_total: null,
      funding_total: null,
      net_pnl_total: null,
      open_exposure: null,
    }));

    const result = await loadAccountPerformance("paper", "all");

    expect(result.mode).toBe("paper");
    expect(fetchMock).toHaveBeenCalledWith(
      "/v1/performance/account/paper?period=all&maximum_points=1000",
      { headers: { Accept: "application/json" }, signal: undefined },
    );
  });
});

describe("trade history API boundary", () => {
  it("loads filtered immutable fills and the matching engine summary", async () => {
    fetchMock
      .mockResolvedValueOnce(jsonResponse([{
        fill_id: 1,
        environment: "paper",
        external_trade_id: "paper-order:fill",
        order_id: "paper-order",
        contract: "BTC_USDT",
        side: "buy",
        position_effect: "open",
        quantity: "0.01",
        price: "65000",
        fee: "0.65",
        role: "taker",
        close_quantity: "0",
        trade_value: "650",
        realized_pnl: "0",
        occurred_at: "2026-07-18T10:00:00Z",
        source: "paper_engine",
        origin: "automatic_strategy",
        instance_id: "strategy-1",
        run_id: "run-1",
        strategy_name_snapshot: "BTC Range",
        ingested_at: "2026-07-18T10:00:01Z",
      }]))
      .mockResolvedValueOnce(jsonResponse({
        fills: 1,
        opened_quantity: "0.01",
        closed_quantity: "0",
        realized_pnl: "0",
        realized_pnl_known_fills: 1,
        winning_fills: 0,
        losing_fills: 0,
        win_rate_percentage: null,
        gross_profit: null,
        gross_loss: null,
        average_win: null,
        average_loss: null,
        profit_factor: null,
        fees: "0.65",
        gross_trade_value: "650",
      }));

    const filters = {
      environment: "paper" as const,
      contract: "BTC_USDT",
      instanceId: "strategy-1",
      since: "2026-07-18T00:00:00Z",
      limit: 1000,
    };
    const history = await loadTradeHistory(filters);
    const summary = await loadTradeHistorySummary(filters);

    expect(history[0]?.strategy_name_snapshot).toBe("BTC Range");
    expect(summary.fills).toBe(1);
    expect(String(fetchMock.mock.calls[0]?.[0])).toContain("/v1/trades?");
    expect(String(fetchMock.mock.calls[0]?.[0])).toContain("instance_id=strategy-1");
    expect(String(fetchMock.mock.calls[1]?.[0])).toContain("/v1/trades/summary?");
  });
});

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function modeState(mode: "live" | "testnet") {
  return {
    mode,
    emergency_stop: false,
    can_enter: false,
    blocked_reasons_ar: [],
    snapshot: null,
  };
}

function accountRisk(environment: "live" | "testnet") {
  return {
    environment,
    day: "2026-07-16",
    baseline_ready: true,
    baseline_equity: "1000",
    current_equity: "1000",
    equity_loss_used: "0",
    remaining_loss_allowance: "100",
    losing_trades: 0,
    automatic_trades: 0,
    policy: {
      daily_loss_limit: "100",
      losing_trade_limit: 3,
      automatic_trade_limit: 5,
      revision: 1,
      updated_at: "2026-07-16T20:00:00Z",
    },
    manual_entries_blocked: false,
    automatic_entries_blocked: false,
    blocked_reason_codes: [],
  };
}

function manualPreview(request: ManualOrderRequest): ManualOrderPreview {
  return {
    request,
    generated_at: "2026-07-16T20:00:00Z",
    last_price: "60000",
    mark_price: "60001",
    best_bid: "59999",
    best_ask: "60001",
    market_data_state: "fresh",
    market_observed_at: "2026-07-16T20:00:00Z",
    available_balance: "1000",
    contract_multiplier: "0.0001",
    quantity_step: "1",
    minimum_quantity: "1",
    minimum_notional: "6",
    approximate_minimum_margin: "1.2",
    maximum_leverage: 100,
    estimated_quantity: "83",
    estimated_notional: "498",
    estimated_margin: "99.6",
    estimated_opening_fee: "0.25",
    estimated_fee_rate: "0.0005",
    estimated_take_profit_price: "66000",
    estimated_stop_loss_price: "63000",
    estimated_liquidation_price: "48000",
    reference_price: "60001",
    limit_distance_percentage: null,
    estimated_liquidity_behavior: "taker",
    supported_time_in_force: ["ioc", "fok"],
    validation_issues: [],
    can_submit: true,
    uses_real_funds: false,
    live_warning_ar: null,
    safety_fingerprint: "a".repeat(64),
  };
}
