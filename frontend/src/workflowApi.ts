import type {
  BotDeployment,
  Environment,
  JsonValue,
  StoredBacktestRun,
  BacktestPortfolioRequest,
  BacktestReadiness,
  StoredPortfolioBacktestRun,
  StrategyCoinSetup,
  StrategyCoinSetupCreate,
  StrategyOpportunity,
  StrategyPreset,
  StrategyPresetCreate,
  StrategyPresetVersion,
  StrategySetupApproval,
  StrategySetupDefaults,
  StrategyTemplate,
  StrategyTemplateCreate,
  WorkflowSummary,
} from "./types";

interface WorkflowRequestOptions extends RequestInit {
  timeoutMs?: number;
}

async function workflowRequest<T>(path: string, options: WorkflowRequestOptions = {}): Promise<T> {
  const { timeoutMs = 15000, signal, ...requestOptions } = options;
  const controller = new AbortController();
  const abortFromParent = () => controller.abort();
  signal?.addEventListener("abort", abortFromParent, { once: true });
  const timeout = window.setTimeout(() => controller.abort(), timeoutMs);
  try {
    const response = await fetch(path, {
      ...requestOptions,
      signal: controller.signal,
      headers: {
        Accept: "application/json",
        ...(requestOptions.body ? { "Content-Type": "application/json" } : {}),
        ...requestOptions.headers,
      },
    });
    const contentType = response.headers.get("content-type") ?? "";
    const body = contentType.includes("application/json") ? await response.json() : await response.text();
    if (!response.ok) {
      const detail = typeof body === "object" && body !== null && "detail" in body
        ? (body as { detail: unknown }).detail
        : body;
      throw new Error(typeof detail === "string" ? detail : `تعذر إكمال الطلب (${response.status})`);
    }
    return body as T;
  } catch (error) {
    if (controller.signal.aborted && !signal?.aborted) {
      throw new Error("Request timed out. Check the failed stage and retry.");
    }
    throw error;
  } finally {
    window.clearTimeout(timeout);
    signal?.removeEventListener("abort", abortFromParent);
  }
}

export function defaultStrategySetupDefaults(): StrategySetupDefaults {
  const marketExit = {
    order_type: "market" as const,
    limit_offset_percentage: null,
    time_in_force: "ioc" as const,
    maximum_wait_seconds: 30,
    fallback_to_market: true,
  };
  return {
    execution_plan: {
      entry: {
        order_type: "market",
        limit_price: null,
        limit_price_formula: null,
        time_in_force: "gtc",
        expires_after_minutes: null,
        cancellation_policy: "cancel_on_signal_reset",
        partial_fill_behavior: "accept_partial",
      },
      take_profit: { ...marketExit },
      stop_loss: { ...marketExit },
      strategy_exit: { ...marketExit },
      manual_exit: { ...marketExit },
    },
    dca: {
      enabled: false,
      maximum_entries: 1,
      spacing_percentage: "1",
      allocation_method: "equal",
      custom_allocations: [],
    },
    risk: {
      requested_margin: "20",
      requested_leverage: 3,
      maximum_positions: 1,
      maximum_exposure_percentage: "25",
    },
  };
}

export function loadWorkflowSummary(signal?: AbortSignal): Promise<WorkflowSummary> {
  return workflowRequest<WorkflowSummary>("/v1/workflow/summary", { signal });
}

export function loadStrategyPresets(
  includeArchived = false,
  signal?: AbortSignal,
): Promise<StrategyPreset[]> {
  return workflowRequest<StrategyPreset[]>(
    `/v1/strategy-presets?include_archived=${includeArchived}`,
    { signal },
  );
}

export function createStrategyPreset(
  change: StrategyPresetCreate,
): Promise<StrategyPreset> {
  return workflowRequest<StrategyPreset>("/v1/strategy-presets", {
    method: "POST",
    body: JSON.stringify(change),
  });
}

export function updateStrategyPreset(
  presetId: string,
  change: Partial<Omit<StrategyPresetCreate, "type_id">>,
): Promise<StrategyPreset> {
  return workflowRequest<StrategyPreset>(
    `/v1/strategy-presets/${encodeURIComponent(presetId)}`,
    {
      method: "PUT",
      body: JSON.stringify(change),
    },
  );
}

export function loadStrategyPresetVersions(
  presetId: string,
  signal?: AbortSignal,
): Promise<StrategyPresetVersion[]> {
  return workflowRequest<StrategyPresetVersion[]>(
    `/v1/strategy-presets/${encodeURIComponent(presetId)}/versions`,
    { signal },
  );
}

export function archiveStrategyPreset(presetId: string): Promise<StrategyPreset> {
  return workflowRequest<StrategyPreset>(
    `/v1/strategy-presets/${encodeURIComponent(presetId)}/archive`,
    { method: "POST" },
  );
}

export function deleteStrategyPreset(presetId: string): Promise<void> {
  return workflowRequest<void>(
    `/v1/strategy-presets/${encodeURIComponent(presetId)}`,
    { method: "DELETE" },
  );
}

/** @deprecated Existing routes remain for compatibility; use Preset APIs. */
export function loadStrategyTemplates(includeArchived = false, signal?: AbortSignal): Promise<StrategyTemplate[]> {
  return workflowRequest<StrategyTemplate[]>(`/v1/strategy-templates?include_archived=${includeArchived}`, { signal });
}

export function createStrategyTemplate(change: StrategyTemplateCreate): Promise<StrategyTemplate> {
  return workflowRequest<StrategyTemplate>("/v1/strategy-templates", {
    method: "POST",
    body: JSON.stringify(change),
  });
}

export function updateStrategyTemplate(
  templateId: string,
  change: Partial<Omit<StrategyTemplateCreate, "type_id">>,
): Promise<StrategyTemplate> {
  return workflowRequest<StrategyTemplate>(`/v1/strategy-templates/${encodeURIComponent(templateId)}`, {
    method: "PUT",
    body: JSON.stringify(change),
  });
}

export function archiveStrategyTemplate(templateId: string): Promise<StrategyTemplate> {
  return workflowRequest<StrategyTemplate>(`/v1/strategy-templates/${encodeURIComponent(templateId)}/archive`, {
    method: "POST",
  });
}

export function deleteStrategyTemplate(templateId: string): Promise<void> {
  return workflowRequest<void>(`/v1/strategy-templates/${encodeURIComponent(templateId)}`, { method: "DELETE" });
}

export function loadStrategySetups(
  templateId?: string,
  includeArchived = false,
  signal?: AbortSignal,
): Promise<StrategyCoinSetup[]> {
  const params = new URLSearchParams({ include_archived: String(includeArchived) });
  if (templateId) params.set("template_id", templateId);
  return workflowRequest<StrategyCoinSetup[]>(`/v1/strategy-setups?${params}`, { signal });
}

export function createStrategySetup(change: StrategyCoinSetupCreate): Promise<StrategyCoinSetup> {
  return workflowRequest<StrategyCoinSetup>("/v1/strategy-setups", {
    method: "POST",
    body: JSON.stringify(change),
  });
}

export function updateStrategySetup(
  setupId: string,
  change: {
    symbol?: string;
    timeframe_minutes?: number;
    direction?: "long" | "short" | "both";
    configuration_overrides?: Record<string, JsonValue>;
    setup_defaults_override?: StrategySetupDefaults | null;
  },
): Promise<StrategyCoinSetup> {
  return workflowRequest<StrategyCoinSetup>(`/v1/strategy-setups/${encodeURIComponent(setupId)}`, {
    method: "PUT",
    body: JSON.stringify(change),
  });
}

export function refreshStrategySetupPrice(setupId: string): Promise<StrategyCoinSetup> {
  return workflowRequest<StrategyCoinSetup>(`/v1/strategy-setups/${encodeURIComponent(setupId)}/refresh-price`, {
    method: "POST",
  });
}

export function resetStrategySetupDefaults(setupId: string): Promise<StrategyCoinSetup> {
  return workflowRequest<StrategyCoinSetup>(`/v1/strategy-setups/${encodeURIComponent(setupId)}/reset-defaults`, {
    method: "POST",
  });
}

export function rebaseStrategySetup(setupId: string): Promise<StrategyCoinSetup> {
  return workflowRequest<StrategyCoinSetup>(`/v1/strategy-setups/${encodeURIComponent(setupId)}/rebase`, {
    method: "POST",
  });
}

export function archiveStrategySetup(setupId: string): Promise<StrategyCoinSetup> {
  return workflowRequest<StrategyCoinSetup>(`/v1/strategy-setups/${encodeURIComponent(setupId)}/archive`, {
    method: "POST",
  });
}

export function deleteStrategySetup(setupId: string): Promise<void> {
  return workflowRequest<void>(`/v1/strategy-setups/${encodeURIComponent(setupId)}`, { method: "DELETE" });
}

export function runSetupBacktest(
  setupId: string,
  request: {
    start: string;
    end: string;
    settings: {
      initial_balance: string;
      margin_per_trade: string;
      leverage: number;
      taker_fee_rate: string;
      slippage_basis_points: string;
      default_take_profit_percentage: string;
      default_stop_loss_percentage: string;
      minimum_trades_for_assessment: number;
    };
  },
): Promise<StoredBacktestRun> {
  return workflowRequest<StoredBacktestRun>(`/v1/strategy-setups/${encodeURIComponent(setupId)}/backtests`, {
    method: "POST",
    body: JSON.stringify(request),
  });
}

export function runPortfolioBacktest(
  request: BacktestPortfolioRequest,
  signal?: AbortSignal,
): Promise<StoredPortfolioBacktestRun> {
  return workflowRequest<StoredPortfolioBacktestRun>("/v1/backtests/portfolio", {
    method: "POST",
    body: JSON.stringify(request),
    signal,
    timeoutMs: 30000,
  });
}

export function checkPortfolioBacktestReadiness(
  request: BacktestPortfolioRequest,
): Promise<BacktestReadiness> {
  return workflowRequest<BacktestReadiness>("/v1/backtests/portfolio/readiness", {
    method: "POST",
    body: JSON.stringify(request),
  });
}

export function loadPortfolioBacktest(
  backtestId: string,
  signal?: AbortSignal,
): Promise<StoredPortfolioBacktestRun> {
  return workflowRequest<StoredPortfolioBacktestRun>(
    `/v1/backtests/portfolio/${encodeURIComponent(backtestId)}`,
    { signal, timeoutMs: 10000 },
  );
}

export function cancelPortfolioBacktest(
  backtestId: string,
): Promise<StoredPortfolioBacktestRun> {
  return workflowRequest<StoredPortfolioBacktestRun>(
    `/v1/backtests/portfolio/${encodeURIComponent(backtestId)}`,
    { method: "DELETE", timeoutMs: 10000 },
  );
}

export function listPortfolioBacktests(limit = 50, signal?: AbortSignal): Promise<StoredPortfolioBacktestRun[]> {
  return workflowRequest<StoredPortfolioBacktestRun[]>(`/v1/backtests/portfolio?limit=${limit}`, { signal });
}

export function updatePortfolioBacktestNotes(
  backtestId: string,
  observations: string,
): Promise<StoredPortfolioBacktestRun> {
  return workflowRequest<StoredPortfolioBacktestRun>(`/v1/backtests/portfolio/${encodeURIComponent(backtestId)}/notes`, {
    method: "PUT",
    body: JSON.stringify({ observations }),
  });
}

export function approveStrategySetup(
  setupId: string,
  mode: Environment,
  note: string,
  options: { acceptNonPromising?: boolean; skipBacktest?: boolean; confirmation?: string } = {},
): Promise<StrategySetupApproval> {
  return workflowRequest<StrategySetupApproval>(`/v1/strategy-setups/${encodeURIComponent(setupId)}/approve`, {
    method: "POST",
    body: JSON.stringify({
      mode,
      note,
      accept_non_promising: options.acceptNonPromising ?? false,
      skip_backtest: options.skipBacktest ?? false,
      confirmation: options.confirmation ?? null,
    }),
  });
}

export function createBotDeployment(setupId: string, environment: Environment): Promise<BotDeployment> {
  return workflowRequest<BotDeployment>(`/v1/strategy-setups/${encodeURIComponent(setupId)}/deployments`, {
    method: "POST",
    body: JSON.stringify({ environment }),
  });
}

export function loadOpportunities(signal?: AbortSignal): Promise<StrategyOpportunity[]> {
  return workflowRequest<StrategyOpportunity[]>("/v1/opportunities", { signal });
}

export function updateOpportunityStatus(
  opportunityId: string,
  status: "reviewed" | "approved" | "rejected" | "ignored" | "expired",
): Promise<StrategyOpportunity> {
  return workflowRequest<StrategyOpportunity>(`/v1/opportunities/${encodeURIComponent(opportunityId)}`, {
    method: "PUT",
    body: JSON.stringify({ status }),
  });
}

export function convertOpportunity(
  opportunityId: string,
  templateId: string,
): Promise<StrategyCoinSetup> {
  return workflowRequest<StrategyCoinSetup>(`/v1/opportunities/${encodeURIComponent(opportunityId)}/convert`, {
    method: "POST",
    body: JSON.stringify({ template_id: templateId, configuration_overrides: {} }),
  });
}

export function loadBotDeployments(signal?: AbortSignal): Promise<BotDeployment[]> {
  return workflowRequest<BotDeployment[]>("/v1/bot-deployments", { signal });
}

export function transitionBotDeployment(
  deploymentId: string,
  action: "start" | "monitor" | "pause" | "stop",
): Promise<BotDeployment> {
  return workflowRequest<BotDeployment>(`/v1/bot-deployments/${encodeURIComponent(deploymentId)}/${action}`, {
    method: "POST",
  });
}
