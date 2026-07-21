import type {
  AccountPerformanceSeries,
  AccountRiskPolicy,
  AccountRiskStatus,
  ActivityEvent,
  ApplicationSettings,
  BacktestEquityPoint,
  BacktestRunRequest,
  BacktestStrategyCreateRequest,
  BacktestTrade,
  BackupDeleteResult,
  BackupRecord,
  BackupRestoreResult,
  DashboardBundle,
  EnvironmentRuntimeState,
  ExchangeCredentialStatus,
  ExchangeCredentialTestResult,
  FixedPriceLadderPreview,
  ManualOrderPreview,
  ManualOrderRequest,
  ManualOrderResult,
  MarketCandleSeries,
  MarketDataSnapshot,
  ModeState,
  PaperAccount,
  PaperPendingEntry,
  PaperPosition,
  PaperRisk,
  PaperWatchlist,
  PrivateStreamState,
  ReconciliationReadiness,
  RemoteData,
  RuntimeState,
  StrategyConfigurationVersion,
  StrategyDecision,
  StrategyInstance,
  StrategyInstanceCreate,
  StrategyOverviewItem,
  StrategyInstanceUpdate,
  StrategyRun,
  StrategyScanRequest,
  StrategyTypeMetadata,
  StoredBacktestRun,
  StoredStrategyScan,
  SupportArchive,
  TradeFill,
  TradeHistorySummary,
} from "./types";

export class ApiError extends Error {
  readonly status: number;
  readonly detail: unknown;
  readonly code: string | null;
  readonly context: Record<string, unknown>;

  constructor(
    status: number,
    message: string,
    detail: unknown,
    code: string | null = null,
    context: Record<string, unknown> = {},
  ) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
    this.code = code;
    this.context = context;
  }
}

async function request<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const response = await fetch(path, {
    ...options,
    headers: {
      Accept: "application/json",
      ...(options.body ? { "Content-Type": "application/json" } : {}),
      ...options.headers,
    },
  });

  const contentType = response.headers.get("content-type") ?? "";
  const body = contentType.includes("application/json")
    ? await response.json()
    : await response.text();

  if (!response.ok) {
    const errorBody = typeof body === "object" && body !== null
      ? body as Record<string, unknown>
      : null;
    const detail = errorBody && "detail" in errorBody ? errorBody.detail : body;
    const code = errorBody && typeof errorBody.code === "string"
      ? errorBody.code
      : errorBody && typeof errorBody.failure_code === "string"
        ? errorBody.failure_code
        : null;
    const context = errorBody && typeof errorBody.context === "object" && errorBody.context !== null
      ? errorBody.context as Record<string, unknown>
      : {};
    const message = typeof detail === "string"
      ? detail
      : errorBody && typeof errorBody.message_ar === "string"
        ? errorBody.message_ar
        : `تعذر إكمال الطلب (${response.status})`;
    throw new ApiError(response.status, message, detail, code, context);
  }
  return body as T;
}

async function settled<T>(promise: Promise<T>): Promise<RemoteData<T>> {
  try {
    return { status: "ready", data: await promise };
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") {
      throw error;
    }
    const message = error instanceof Error ? error.message : "خطأ غير معروف";
    return { status: "error", message };
  }
}

async function optional<T>(promise: Promise<T>): Promise<T | null> {
  try {
    return await promise;
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) {
      return null;
    }
    throw error;
  }
}

export async function loadDashboard(
  signal?: AbortSignal,
): Promise<DashboardBundle> {
  const options = { signal } satisfies RequestInit;
  const [
    runtime,
    settings,
    strategyTypes,
    strategies,
    strategyOverview,
    liveState,
    testnetState,
    liveRisk,
    testnetRisk,
    privateStream,
    paperAccount,
    paperPerformance,
    paperRisk,
    paperPosition,
    paperPendingEntry,
    watchlist,
    activity,
  ] = await Promise.all([
    settled(request<RuntimeState>("/health", options)),
    settled(request<ApplicationSettings>("/v1/settings", options)),
    settled(request<StrategyTypeMetadata[]>("/v1/strategy-types", options)),
    settled(request<StrategyInstance[]>("/v1/strategies", options)),
    settled(request<StrategyOverviewItem[]>("/v1/strategies/overview", options)),
    settled(request<ModeState>("/v1/exchange/live/state", options)),
    settled(request<ModeState>("/v1/exchange/testnet/state", options)),
    settled(request<AccountRiskStatus>("/v1/account-risk/live", options)),
    settled(request<AccountRiskStatus>("/v1/account-risk/testnet", options)),
    settled(request<PrivateStreamState>("/v1/exchange/private-stream", options)),
    settled(request<PaperAccount>("/v1/paper-account", options)),
    settled(
      request<AccountPerformanceSeries>(
        "/v1/performance/account/paper?period=all&maximum_points=2",
        options,
      ),
    ),
    settled(request<PaperRisk>("/v1/paper/risk", options)),
    settled(optional(request<PaperPosition>("/v1/paper/position", options))),
    settled(request<PaperPendingEntry | null>("/v1/paper/pending-entry-state", options)),
    settled(request<PaperWatchlist>("/v1/paper/watchlist", options)),
    settled(request<ActivityEvent[]>("/v1/activity?limit=200", options)),
  ]);

  return {
    runtime,
    settings,
    strategyTypes,
    strategies,
    strategyOverview,
    liveState,
    testnetState,
    liveRisk,
    testnetRisk,
    privateStream,
    paperAccount,
    paperPerformance,
    paperRisk,
    paperPosition,
    paperPendingEntry,
    watchlist,
    activity,
    loadedAt: new Date().toISOString(),
  };
}

export function listStrategyTypes(signal?: AbortSignal): Promise<StrategyTypeMetadata[]> {
  return request<StrategyTypeMetadata[]>("/v1/strategy-types", { signal });
}

export function previewFixedPriceLadder(
  configuration: Record<string, unknown>,
): Promise<FixedPriceLadderPreview> {
  return request<FixedPriceLadderPreview>(
    "/v1/strategies/fixed-price-ladder/preview",
    { method: "POST", body: JSON.stringify(configuration) },
  );
}

export function loadAccountPerformance(
  environment: "paper" | "testnet" | "live",
  period: "today" | "7d" | "30d" | "all",
  signal?: AbortSignal,
): Promise<AccountPerformanceSeries> {
  return request<AccountPerformanceSeries>(
    `/v1/performance/account/${environment}?period=${period}&maximum_points=1000`,
    { signal },
  );
}

export interface TradeHistoryFilters {
  environment?: "paper" | "testnet" | "live";
  contract?: string;
  instanceId?: string;
  runId?: string;
  since?: string;
  limit?: number;
}

function tradeHistoryQuery(filters: TradeHistoryFilters): string {
  const query = new URLSearchParams();
  if (filters.environment) query.set("environment", filters.environment);
  if (filters.contract) query.set("contract", filters.contract);
  if (filters.instanceId) query.set("instance_id", filters.instanceId);
  if (filters.runId) query.set("run_id", filters.runId);
  if (filters.since) query.set("since", filters.since);
  query.set("limit", String(filters.limit ?? 500));
  return query.toString();
}

export function loadTradeHistory(
  filters: TradeHistoryFilters,
  signal?: AbortSignal,
): Promise<TradeFill[]> {
  return request<TradeFill[]>(`/v1/trades?${tradeHistoryQuery(filters)}`, { signal });
}

export function loadTradeHistorySummary(
  filters: Omit<TradeHistoryFilters, "limit">,
  signal?: AbortSignal,
): Promise<TradeHistorySummary> {
  const query = tradeHistoryQuery({ ...filters, limit: 500 });
  return request<TradeHistorySummary>(`/v1/trades/summary?${query}`, { signal });
}

export function loadMarketCandles(
  symbol: string,
  timeframeMinutes: number,
  signal?: AbortSignal,
): Promise<MarketCandleSeries> {
  return request<MarketCandleSeries>(
    `/v1/market-data/${encodeURIComponent(symbol)}/candles/${timeframeMinutes}`,
    { signal },
  );
}

export function loadMarketSnapshot(
  symbol: string,
  signal?: AbortSignal,
): Promise<MarketDataSnapshot> {
  return request<MarketDataSnapshot>(
    `/v1/market-data/${encodeURIComponent(symbol)}`,
    { signal },
  );
}

export function cancelPaperPendingEntry(): Promise<PaperAccount> {
  return request<PaperAccount>("/v1/paper/pending-entry", {
    method: "DELETE",
  });
}

export function saveApplicationSettings(
  settings: Omit<ApplicationSettings, "revision" | "updated_at">,
): Promise<ApplicationSettings> {
  return request<ApplicationSettings>("/v1/settings", {
    method: "PUT",
    body: JSON.stringify(settings),
  });
}

export function switchRuntimeEnvironment(
  environment: "paper" | "testnet" | "live",
  confirmation = "",
): Promise<EnvironmentRuntimeState> {
  return request<EnvironmentRuntimeState>("/v1/runtime/environment/switch", {
    method: "POST",
    body: JSON.stringify({ environment, confirmation }),
  });
}

export function loadReconciliationReadiness(
  mode: "testnet" | "live",
  signal?: AbortSignal,
): Promise<ReconciliationReadiness> {
  return request<ReconciliationReadiness>(
    `/v1/exchange/${mode}/reconciliation`,
    { signal },
  );
}

export function requestReconciliation(
  mode: "testnet" | "live",
): Promise<ModeState> {
  return request<ModeState>(`/v1/exchange/${mode}/reconcile`, {
    method: "POST",
  });
}

export function loadAccountRiskPolicy(
  signal?: AbortSignal,
): Promise<AccountRiskPolicy> {
  return request<AccountRiskPolicy>("/v1/account-risk/policy", { signal });
}

export function saveAccountRiskPolicy(
  policy: Pick<
    AccountRiskPolicy,
    | "daily_loss_enabled"
    | "daily_loss_limit"
    | "losing_trade_enabled"
    | "losing_trade_limit"
    | "automatic_trade_enabled"
    | "automatic_trade_limit"
  > & { confirmation?: string },
): Promise<AccountRiskPolicy> {
  return request<AccountRiskPolicy>("/v1/account-risk/policy", {
    method: "PUT",
    body: JSON.stringify(policy),
  });
}

export function loadCredentialStatus(
  mode: "testnet" | "live",
  signal?: AbortSignal,
): Promise<ExchangeCredentialStatus> {
  return request<ExchangeCredentialStatus>(
    `/v1/exchange/${mode}/credentials`,
    { signal },
  );
}

export function saveCredentials(
  mode: "testnet" | "live",
  apiKey: string,
  apiSecret: string,
): Promise<ExchangeCredentialStatus> {
  return request<ExchangeCredentialStatus>("/v1/exchange/credentials", {
    method: "POST",
    body: JSON.stringify({ mode, api_key: apiKey, api_secret: apiSecret }),
  });
}

export function testCredentials(
  mode: "testnet" | "live",
): Promise<ExchangeCredentialTestResult> {
  return request<ExchangeCredentialTestResult>(
    `/v1/exchange/${mode}/credentials/test`,
    { method: "POST" },
  );
}

export function removeCredentials(
  mode: "testnet" | "live",
): Promise<ExchangeCredentialStatus> {
  return request<ExchangeCredentialStatus>(
    `/v1/exchange/${mode}/credentials`,
    { method: "DELETE" },
  );
}

export function createStrategy(
  strategy: StrategyInstanceCreate,
): Promise<StrategyInstance> {
  return request<StrategyInstance>("/v1/strategies", {
    method: "POST",
    body: JSON.stringify(strategy),
  });
}

export function updateStrategy(
  instanceId: string,
  change: StrategyInstanceUpdate,
): Promise<StrategyInstance> {
  return request<StrategyInstance>(`/v1/strategies/${encodeURIComponent(instanceId)}`, {
    method: "PUT",
    body: JSON.stringify(change),
  });
}

export function duplicateStrategy(
  instanceId: string,
  name?: string,
): Promise<StrategyInstance> {
  return request<StrategyInstance>(
    `/v1/strategies/${encodeURIComponent(instanceId)}/duplicate`,
    {
      method: "POST",
      body: JSON.stringify(name ? { name } : {}),
    },
  );
}

export async function deleteStrategy(instanceId: string): Promise<void> {
  await request<unknown>(`/v1/strategies/${encodeURIComponent(instanceId)}`, {
    method: "DELETE",
  });
}

export function loadStrategyRuns(
  instanceId: string,
  signal?: AbortSignal,
): Promise<StrategyRun[]> {
  return request<StrategyRun[]>(
    `/v1/strategies/${encodeURIComponent(instanceId)}/runs`,
    { signal },
  );
}

export function loadStrategyConfigurationVersions(
  instanceId: string,
  signal?: AbortSignal,
): Promise<StrategyConfigurationVersion[]> {
  return request<StrategyConfigurationVersion[]>(
    `/v1/strategies/${encodeURIComponent(instanceId)}/configuration-versions`,
    { signal },
  );
}

export function loadStrategyDecisions(
  instanceId: string,
  signal?: AbortSignal,
): Promise<StrategyDecision[]> {
  return request<StrategyDecision[]>(
    `/v1/strategies/${encodeURIComponent(instanceId)}/decisions?limit=20`,
    { signal },
  );
}

export function previewManualOrder(
  order: ManualOrderRequest,
): Promise<ManualOrderPreview> {
  return request<ManualOrderPreview>("/v1/manual-orders/preview", {
    method: "POST",
    body: JSON.stringify(order),
  });
}

export function submitManualOrder(
  preview: ManualOrderPreview,
): Promise<ManualOrderResult> {
  return request<ManualOrderResult>("/v1/manual-orders", {
    method: "POST",
    body: JSON.stringify({
      request: preview.request,
      preview_fingerprint: preview.safety_fingerprint,
    }),
  });
}

export function transitionStrategy(
  instanceId: string,
  action: "start" | "monitor" | "pause" | "stop",
): Promise<StrategyInstance> {
  return request<StrategyInstance>(
    `/v1/strategies/${encodeURIComponent(instanceId)}/${action}`,
    { method: "POST" },
  );
}

export function runDiscoveryScan(
  scan: StrategyScanRequest,
): Promise<StoredStrategyScan> {
  return request<StoredStrategyScan>("/v1/discovery/scans", {
    method: "POST",
    body: JSON.stringify(scan),
  });
}

export function listDiscoveryScans(signal?: AbortSignal): Promise<StoredStrategyScan[]> {
  return request<StoredStrategyScan[]>("/v1/discovery/scans", { signal });
}

export function runBacktest(
  backtest: BacktestRunRequest,
): Promise<StoredBacktestRun> {
  return request<StoredBacktestRun>("/v1/backtests", {
    method: "POST",
    body: JSON.stringify(backtest),
  });
}

export function listBacktests(signal?: AbortSignal): Promise<StoredBacktestRun[]> {
  return request<StoredBacktestRun[]>("/v1/backtests", { signal });
}

export function loadBacktestTrades(
  backtestId: string,
  signal?: AbortSignal,
): Promise<BacktestTrade[]> {
  return request<BacktestTrade[]>(
    `/v1/backtests/${encodeURIComponent(backtestId)}/trades`,
    { signal },
  );
}

export function loadBacktestEquity(
  backtestId: string,
  signal?: AbortSignal,
): Promise<BacktestEquityPoint[]> {
  return request<BacktestEquityPoint[]>(
    `/v1/backtests/${encodeURIComponent(backtestId)}/equity`,
    { signal },
  );
}

export function createStrategyFromBacktest(
  backtestId: string,
  requestBody: BacktestStrategyCreateRequest,
): Promise<StrategyInstance> {
  return request<StrategyInstance>(
    `/v1/backtests/${encodeURIComponent(backtestId)}/create-strategy`,
    {
      method: "POST",
      body: JSON.stringify(requestBody),
    },
  );
}

export function listBackups(signal?: AbortSignal): Promise<BackupRecord[]> {
  return request<BackupRecord[]>("/v1/backups", { signal });
}

export function createBackup(): Promise<BackupRecord> {
  return request<BackupRecord>("/v1/backups", { method: "POST" });
}

export function deleteBackup(name: string): Promise<BackupDeleteResult> {
  return request<BackupDeleteResult>(`/v1/backups/${encodeURIComponent(name)}`, {
    method: "DELETE",
  });
}

export function restoreBackup(name: string): Promise<BackupRestoreResult> {
  return request<BackupRestoreResult>(
    `/v1/backups/${encodeURIComponent(name)}/restore`,
    {
      method: "POST",
      body: JSON.stringify({ confirmation: "RESTORE RANGEBOT" }),
    },
  );
}

export async function exportSupportLogs(): Promise<SupportArchive> {
  const response = await fetch("/v1/logs/export", { method: "POST" });
  if (!response.ok) {
    const contentType = response.headers.get("content-type") ?? "";
    const body = contentType.includes("application/json")
      ? await response.json()
      : await response.text();
    const detail = typeof body === "object" && body !== null && "detail" in body
      ? (body as { detail: unknown }).detail
      : body;
    throw new ApiError(
      response.status,
      typeof detail === "string" ? detail : `تعذر تصدير السجلات (${response.status})`,
      detail,
    );
  }
  const disposition = response.headers.get("content-disposition") ?? "";
  const filenameMatch = disposition.match(/filename\*?=(?:UTF-8''|\")?([^\";]+)/i);
  return {
    blob: await response.blob(),
    filename: filenameMatch?.[1] ?? "rangebot-support.zip",
  };
}
