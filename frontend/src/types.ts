export type Environment = "paper" | "testnet" | "live";
export type JsonValue = string | number | boolean | null | JsonValue[] | { [key: string]: JsonValue };

export interface EngineEvent {
  event_id: string;
  sequence: number;
  category:
    | "engine"
    | "account"
    | "order"
    | "strategy"
    | "market"
    | "settings"
    | "credentials"
    | "backup"
    | "activity";
  action: string;
  resource: string;
  occurred_at: string;
}

export type RemoteData<T> =
  | { status: "loading" }
  | { status: "ready"; data: T }
  | { status: "error"; message: string };

export type EnvironmentTransitionState =
  | "ready"
  | "switching"
  | "restart_required"
  | "failed"
  | "mismatch";

export interface EnvironmentRuntimeState {
  configured_environment: Environment;
  requested_environment: Environment;
  active_engine_environment: Environment;
  exchange_adapter_environment: "testnet" | "live" | null;
  public_rest_environment: "testnet" | "live" | null;
  public_websocket_environment: "testnet" | "live" | null;
  private_websocket_environment: "testnet" | "live" | null;
  credential_profile: "testnet" | "live" | null;
  transition_state: EnvironmentTransitionState;
  restart_required: boolean;
  activated: boolean;
  transition_started_at: string | null;
  transition_completed_at: string | null;
  failure_code: string | null;
  message_ar: string | null;
  revision: number;
}

export interface RuntimeState {
  lifecycle: string;
  started_at: string;
  last_heartbeat_at: string;
  state_revision: number;
  environment: EnvironmentRuntimeState | null;
}

export interface ApplicationSettings {
  environment: Environment;
  ui_language: "ar" | "en";
  dashboard_layout: Record<string, JsonValue>;
  dashboard_filters: Record<string, JsonValue>;
  sidebar_preferences: Record<string, JsonValue>;
  application_preferences: Record<string, JsonValue>;
  revision: number;
  updated_at: string | null;
}

export interface ExchangePositionSnapshot {
  contract: string;
  side: "long" | "short";
  quantity: string;
  entry_price: string | null;
  mark_price: string | null;
  value: string;
  margin: string;
  unrealized_pnl: string;
  realized_pnl: string;
  liquidation_price: string | null;
  leverage: string | null;
  pending_orders: number;
  opened_at: string | null;
  updated_at: string | null;
  managed_by_rangebot: boolean;
  origin: "manual" | "automatic_strategy" | "monitoring_conversion" | "legacy_automatic" | null;
  instance_id: string | null;
  run_id: string | null;
  strategy_name: string | null;
  ownership_created_at: string | null;
  trailing_stop_price: string | null;
  trailing_stop_distance: string | null;
  trailing_state: "desired" | "active" | "error" | null;
  trailing_order_id: string | null;
  trailing_last_error: string | null;
}

export interface ExchangeOpenOrderSnapshot {
  order_id: string;
  contract: string;
  side: "long" | "short";
  order_type: "market" | "limit";
  price: string | null;
  quantity: string;
  filled_quantity: string;
  status: string;
  reduce_only: boolean;
  created_at: string | null;
  managed_by_rangebot: boolean;
  origin: "manual" | "automatic_strategy" | "monitoring_conversion" | "legacy_automatic" | null;
  instance_id: string | null;
  run_id: string | null;
  strategy_name: string | null;
}

export interface MarketCandle {
  opened_at: string;
  closed_at: string;
  open: string;
  high: string;
  low: string;
  close: string;
  volume: string;
  closed: boolean;
}

export interface MarketCandleSeries {
  symbol: string;
  timeframe_minutes: number;
  candles: MarketCandle[];
  source: "gate_rest" | "gate_websocket";
  updated_at: string;
}

export interface PublicContract {
  symbol: string;
  quantity_step: string;
  minimum_quantity: string;
}

export interface MarketDataSnapshot {
  symbol: string;
  last_price: string;
  mark_price: string | null;
  best_bid: string | null;
  best_ask: string | null;
  volume_24h: string | null;
  funding_rate: string | null;
  observed_at: string;
  received_at: string;
  source: "gate_rest" | "gate_websocket";
  sequence: number | null;
  state: "fresh" | "stale" | "reconnecting" | "unavailable";
  state_reason: string | null;
  sequence_gap: boolean;
  last_update_age_seconds: string;
}

export interface ExchangeSnapshot {
  mode: "testnet" | "live";
  reconciled_at: string;
  available_futures_balance: string;
  total_futures_balance: string;
  total_futures_equity: string;
  unrealized_pnl: string;
  position_margin: string;
  order_margin: string;
  used_margin: string;
  margin_usage_percentage: string;
  realized_pnl_total: string;
  fees_total: string;
  funding_total: string;
  net_pnl_total: string;
  open_exposure: string;
  position_quantity: string;
  liquidation_price: string | null;
  positions: ExchangePositionSnapshot[];
  open_orders: ExchangeOpenOrderSnapshot[];
  managed_order_ids: string[];
  unmanaged_state: boolean;
  reconciliation_error: string | null;
  one_way_confirmed: boolean;
  cross_margin_confirmed: boolean;
  leverage_confirmed: number | null;
  market_ready: boolean;
  history_ready: boolean;
  risk_ready: boolean;
  active_contract_ready: boolean;
  daily_baseline_ready: boolean;
  protection_ready: boolean;
  trailing_protection_ready: boolean | null;
  trailing_reconciliation_ready: boolean;
  trailing_order_ids: string[];
  tp_enabled: boolean;
  sl_enabled: boolean;
  subscription_confirmed: boolean;
  rest_snapshot_confirmed: boolean;
  websocket_price_updates: number;
  market_observed_at: string | null;
}

export interface ModeState {
  mode: "testnet" | "live";
  emergency_stop: boolean;
  can_enter: boolean;
  blocked_reasons_ar: string[];
  snapshot: ExchangeSnapshot | null;
}

export interface ReconciliationReadiness {
  mode: "testnet" | "live";
  state: "ready" | "refreshing" | "stale" | "missing" | "failed";
  ready: boolean;
  refresh_in_progress: boolean;
  snapshot_age_seconds: number | null;
  maximum_snapshot_age_seconds: number;
  last_attempt_at: string | null;
  last_success_at: string | null;
  attempt_count: number;
  failure_code: string | null;
  message_ar: string | null;
  reason_codes: string[];
  snapshot: ExchangeSnapshot | null;
}

export interface ExchangeCredentialStatus {
  mode: "testnet" | "live";
  configured: boolean;
}

export interface ExchangeCredentialTestResult {
  mode: "testnet" | "live";
  valid: boolean;
  message_ar: string;
}

export type BackupKind = "manual" | "pre_migration" | "pre_restore" | "lifecycle";

export interface BackupRecord {
  name: string;
  kind: BackupKind;
  created_at: string;
  size_bytes: number;
}

export interface BackupDeleteResult {
  name: string;
  deleted: boolean;
  message_ar: string;
}

export interface BackupRestoreResult {
  restored: BackupRecord;
  safety_backup: BackupRecord;
  reconciled_mode: "testnet" | "live" | null;
  reconciliation_succeeded: boolean;
  emergency_stop_active: boolean;
  message_ar: string;
}

export interface TradeFill {
  fill_id: number;
  environment: Environment;
  external_trade_id: string;
  order_id: string | null;
  contract: string;
  side: "buy" | "sell";
  position_effect: "open" | "close" | "mixed" | "unknown";
  quantity: string;
  price: string;
  fee: string;
  role: "maker" | "taker" | "unknown";
  close_quantity: string;
  trade_value: string;
  realized_pnl: string | null;
  occurred_at: string;
  source: "paper_engine" | "gate_rest";
  origin: "manual" | "automatic_strategy" | "monitoring_conversion" | "legacy_automatic" | "external" | null;
  instance_id: string | null;
  run_id: string | null;
  strategy_name_snapshot: string | null;
  ingested_at: string;
}

export interface TradeHistorySummary {
  fills: number;
  opened_quantity: string;
  closed_quantity: string;
  realized_pnl: string | null;
  realized_pnl_known_fills: number;
  winning_fills: number;
  losing_fills: number;
  win_rate_percentage: string | null;
  gross_profit: string | null;
  gross_loss: string | null;
  average_win: string | null;
  average_loss: string | null;
  profit_factor: string | null;
  fees: string;
  gross_trade_value: string;
}

export interface SupportArchive {
  blob: Blob;
  filename: string;
}

export interface StrategyFieldMetadata {
  key: string;
  label_ar: string;
  label_en: string;
  value_type: string;
  unit: string | null;
}

export interface StrategyTypeMetadata {
  type_id: string;
  display_name_ar: string;
  display_name_en: string;
  description_ar: string;
  description_en: string;
  version: string;
  supports_monitoring: boolean;
  supports_automatic_trading: boolean;
  supports_long: boolean;
  supports_short: boolean;
  supported_directions: string[];
  supported_timeframes: number[];
  required_market_data_feeds: string[];
  implementation_status: "working" | "experimental" | "disabled";
  supports_scanning: boolean;
  supports_backtesting: boolean;
  minimum_backtest_candles: number;
  configuration_schema: Record<string, JsonValue>;
  candidate_metrics: StrategyFieldMetadata[];
  summary_metrics: StrategyFieldMetadata[];
  live_analysis_fields: StrategyFieldMetadata[];
  recommended_widgets: string[];
  chart_overlays: string[];
  status_badges: string[];
  important_warnings_ar: string[];
}

export interface FixedPriceLadderPreview {
  contract_symbol: string;
  environment: Environment;
  total_budget: string;
  budget_basis: string;
  total_allocated_margin: string;
  total_estimated_fee_reserve: string;
  safety_reserve: string;
  total_required_balance: string;
  available_balance: string | null;
  market_price: string | null;
  contract_multiplier: string;
  quantity_step: string;
  minimum_quantity: string;
  price_tick: string;
  leverage: number;
  margin_mode: string;
  current_liquidation_price: string | null;
  levels: Array<{
    level_id: string;
    price: string;
    allocation: string;
    allocated_margin: string;
    notional_value: string;
    contract_quantity: string;
    underlying_quantity: string;
    estimated_entry_fee: string;
    cumulative_filled_quantity: string;
    projected_average_entry: string | null;
    projected_take_profit_price: string | null;
    projected_stop_loss_price: string | null;
    projected_position_value: string;
    projected_liquidation_price: string | null;
    liquidation_distance: string | null;
    issues: Array<{ code: string; message: string; level_id: string | null }>;
  }>;
  issues: Array<{ code: string; message: string; level_id: string | null }>;
  warnings: string[];
  can_activate: boolean;
}

export interface StrategyScanRequest {
  strategy_type_id: string;
  timeframe_minutes: number;
  configuration: Record<string, JsonValue>;
  minimum_quote_volume: string;
  maximum_symbols: number;
  maximum_candidates: number;
  minimum_score: number;
}

export interface StrategyScanCandidate {
  symbol: string;
  exchange: string;
  market_type: "usdt_perpetual";
  quote_currency: string;
  current_price: string | null;
  price_observed_at: string | null;
  score: number;
  signal: "long" | "short" | "none";
  eligible_now: boolean;
  evaluated_at: string;
  market_data_state: "fresh" | "stale" | "reconnecting" | "unavailable";
  explanation_ar: string;
  reason_codes: string[];
  warnings: string[];
  metrics: Record<string, JsonValue>;
  completed_candles: number;
  backtest_ready: boolean;
}

export interface StrategyScanFailure {
  symbol: string;
  reason_code: string;
  explanation_ar: string;
}

export interface StrategyScanResult {
  strategy_type_id: string;
  timeframe_minutes: number;
  scanned_at: string;
  universe_symbols: number;
  scanned_symbols: number;
  candidates: StrategyScanCandidate[];
  failures: StrategyScanFailure[];
}

export interface StoredStrategyScan {
  scan_id: string;
  strategy_version: string;
  created_at: string;
  request: StrategyScanRequest;
  result: StrategyScanResult;
}

export interface BacktestSettings {
  initial_balance: string;
  margin_per_trade: string;
  leverage: number;
  maker_fee_rate?: string;
  taker_fee_rate: string;
  slippage_basis_points: string;
  default_take_profit_percentage: string;
  default_stop_loss_percentage: string;
  minimum_trades_for_assessment: number;
  spread_basis_points?: string;
  ambiguity_policy?: "conservative" | "optimistic" | "lower_timeframe" | "mark_ambiguous";
  position_sizing_mode?: "fixed_quote" | "percentage_available" | "percentage_starting" | "risk_based";
  position_size_percentage?: string;
  risk_percentage?: string;
  maximum_positions?: number;
  maximum_allocation_percentage?: string;
}

export interface BacktestExecutionSettings {
  entry_expiration_candles: number | null;
  time_exit_candles: number | null;
  take_profit_order_type: "market" | "limit";
  stop_loss_order_type: "market" | "limit";
  take_profit_percentage: string | null;
  stop_loss_percentage: string | null;
  dca_enabled: boolean;
  dca_spacing_percentage: string;
  dca_allocations: string[];
  recalculate_target_after_dca: boolean;
  cooldown_candles: number;
}

export interface BacktestPortfolioRequest {
  mode: "manual_symbols" | "historical_scanner";
  setup_id: string | null;
  setup_revision: number | null;
  strategy_type_id: string;
  strategy_version: string;
  scanner_version: string | null;
  exchange: "gateio";
  market_type: "usdt_perpetual";
  quote_currency: "USDT";
  symbols: string[];
  timeframe_minutes: number;
  additional_timeframes: number[];
  configuration: Record<string, JsonValue>;
  parameter_overrides: Record<string, JsonValue>;
  start: string;
  end: string;
  warmup_candles: number;
  scan_frequency_candles: number;
  maximum_candidates: number;
  universe_quality: "exact_historical" | "approximate_historical" | "current_survivor";
  data_provider: string;
  data_version: string | null;
  code_version: string | null;
  pre_test_hypothesis: string;
  execution: BacktestExecutionSettings;
  settings: BacktestSettings;
}

export interface BacktestReadiness {
  ready: boolean;
  missing_rules: string[];
  warnings: string[];
}

export interface BacktestRunRequest {
  scan_id?: string | null;
  setup_id?: string | null;
  setup_revision?: number | null;
  strategy_type_id: string;
  symbol: string;
  timeframe_minutes: number;
  configuration: Record<string, JsonValue>;
  start: string;
  end: string;
  settings: BacktestSettings;
}

export interface BacktestTrade {
  trade_number: number;
  symbol?: string;
  direction: "long" | "short";
  signal_at: string;
  entered_at: string;
  exited_at: string;
  entry_price: string;
  exit_price: string;
  quantity: string;
  allocated_margin: string;
  leverage: number;
  gross_pnl: string;
  fees: string;
  funding: string;
  net_pnl: string;
  return_on_margin_percentage: string;
  exit_reason: "take_profit" | "stop_loss" | "trailing_stop" | "time_exit" | "end_of_data";
  bars_held: number;
  average_entry_price?: string | null;
  result_r?: string | null;
  slippage?: string;
  ambiguous?: boolean;
  entry_explanation_ar?: string;
  take_profit_price?: string | null;
  stop_loss_price?: string | null;
  entry_fills?: Array<{
    fill_id: string;
    role: "entry" | "dca";
    filled_at: string;
    price: string;
    quantity: string;
    fee: string;
    slippage_amount: string;
  }>;
}

export interface BacktestEquityPoint {
  occurred_at: string;
  equity: string;
  drawdown_percentage: string;
  cash?: string | null;
  invested_capital?: string;
}

export interface BacktestMetrics {
  starting_balance: string;
  ending_balance: string;
  net_profit: string;
  return_percentage: string;
  total_trades: number;
  winning_trades: number;
  losing_trades: number;
  win_rate_percentage: string;
  gross_profit: string;
  gross_loss: string;
  fees: string;
  funding: string;
  average_win: string;
  average_loss: string;
  profit_factor: string | null;
  maximum_drawdown_percentage: string;
  maximum_losing_streak: number;
  long_net_pnl: string;
  short_net_pnl: string;
  largest_winner_share_percentage: string | null;
  gross_return_percentage?: string;
  ending_equity?: string | null;
  expectancy?: string;
  average_r?: string | null;
  largest_win?: string;
  largest_loss?: string;
  maximum_winning_streak?: number;
  total_fees?: string;
  total_slippage?: string;
  average_holding_seconds?: string;
  exposure_percentage?: string;
  ambiguous_trades?: number;
}

export interface BacktestAssessment {
  label: "promising" | "mixed" | "weak" | "insufficient_data";
  score: number;
  summary_ar: string;
  reasons: string[];
  warnings: string[];
}

export interface BacktestResult {
  spec: {
    strategy_type_id: string;
    symbol: string;
    timeframe_minutes: number;
    configuration: Record<string, JsonValue>;
    settings: BacktestSettings;
  };
  started_at: string;
  ended_at: string;
  candle_count: number;
  trades: BacktestTrade[];
  equity_curve: BacktestEquityPoint[];
  metrics: BacktestMetrics;
  assessment: BacktestAssessment;
  warnings: string[];
  candidates?: Array<{ occurred_at: string; symbol: string; score: number; rank: number; qualified: boolean; selected: boolean; factor_values: Record<string, JsonValue>; explanation_ar: string; rejection_reason: string | null }>;
  decisions?: Array<{ decision_id: string; occurred_at: string; symbol: string; event: string; qualified: boolean; selected: boolean; explanation_ar: string }>;
  orders?: Array<{ order_id: string; symbol: string; role: string; order_type: string; submitted_at: string; quantity: string; status: string; rejection_reason: string | null }>;
  fills?: Array<{ fill_id: string; symbol: string; role: string; filled_at: string; price: string; quantity: string; fee: string; slippage_amount: string }>;
}

export interface StoredPortfolioBacktestRun {
  backtest_id: string;
  status: "queued" | "loading_data" | "running" | "calculating_results" | "completed" | "failed" | "canceled";
  progress_percentage: number;
  stage_message_ar: string;
  configuration_hash: string;
  input_data_hash: string | null;
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
  request: BacktestPortfolioRequest;
  result: BacktestResult | null;
  failure_reason: string | null;
  post_test_observations: string;
}

export interface StoredBacktestRun {
  backtest_id: string;
  scan_id: string | null;
  strategy_version: string;
  created_at: string;
  request: BacktestRunRequest;
  result: BacktestResult;
  applied_instance_id: string | null;
}

export interface BacktestStrategyCreateRequest {
  name: string;
  environment: Environment;
  direction: "long_only" | "short_only" | "both";
}

export type StrategyStatus = "stopped" | "running" | "monitoring" | "paused" | "error";

export interface BuiltInStrategyTemplate {
  template_id: string;
  type_id: string;
  name: string;
  description: string;
  version: string;
  immutable: true;
  supports_monitoring: boolean;
  supports_automatic_trading: boolean;
  supports_backtesting: boolean;
  supports_scanning: boolean;
  supported_directions: string[];
  supported_timeframes: number[];
  configuration_schema: Record<string, JsonValue>;
}

export interface StrategyInstanceFromTemplateCreate {
  template_id: string;
  preset_id?: string | null;
  name: string;
  environment: Environment;
  symbol: string;
  timeframe_minutes?: number | null;
  direction?: "long" | "short" | "both" | null;
  requested_margin?: string | null;
  requested_leverage?: number | null;
  configuration_overrides?: Record<string, JsonValue>;
}

export interface StrategyInstanceCreate {
  type_id: string;
  template_id?: string | null;
  preset_id?: string | null;
  name: string;
  environment: Environment;
  symbol: string;
  timeframe_minutes: number;
  direction: "long" | "short" | "both";
  requested_margin: string;
  requested_leverage: number;
  configuration: Record<string, JsonValue>;
}

export interface StrategyInstanceUpdate {
  name?: string;
  environment?: Environment;
  symbol?: string;
  timeframe_minutes?: number;
  direction?: "long" | "short" | "both";
  requested_margin?: string;
  requested_leverage?: number;
  configuration?: Record<string, JsonValue>;
}

export interface StrategyConfigurationVersion {
  version_id: number;
  instance_id: string;
  revision: number;
  requested_margin: string;
  requested_leverage: number;
  configuration: Record<string, JsonValue>;
  created_at: string;
}

export interface StrategyRun {
  run_id: string;
  instance_id: string;
  mode: "automatic" | "monitoring";
  status: "active" | "completed" | "error";
  configuration_revision: number;
  configuration_snapshot: Record<string, JsonValue>;
  started_at: string;
  ended_at: string | null;
  end_reason: string | null;
}

export interface StrategyStartReadiness {
  instance_id: string;
  environment: Environment;
  ready: boolean;
  backtest_state:
    | "never_backtested"
    | "current_successful"
    | "current_failed"
    | "stale";
  backtest_id: string | null;
  backtest_assessment: "promising" | "mixed" | "weak" | "insufficient_data" | null;
  blocker_codes: string[];
  warning_codes: string[];
  checks: Record<string, boolean>;
  messages_ar: Record<string, string>;
}

export interface StrategyDeletionReadiness {
  instance_id: string;
  can_delete: boolean;
  must_archive: boolean;
  reason_codes: string[];
  messages: Record<string, string>;
}

export interface StrategyInstance {
  type_id: string;
  template_id: string;
  template_version: string;
  preset_id: string | null;
  preset_revision: number | null;
  name: string;
  environment: Environment;
  symbol: string;
  timeframe_minutes: number;
  direction: "long" | "short" | "both";
  requested_margin: string;
  requested_leverage: number;
  configuration: Record<string, JsonValue>;
  instance_id: string;
  status: StrategyStatus;
  is_pinned: boolean;
  archived_at: string | null;
  archive_reason: string | null;
  created_at: string;
  updated_at: string;
  revision: number;
}

export interface StrategyOverviewItem extends StrategyInstance {
  current_signal: string | null;
  latest_decision_eligible: boolean | null;
  latest_reason_codes: string[];
  last_decision_at: string | null;
  today_realized_pnl: string | null;
  total_realized_pnl: string | null;
  win_rate_percentage: string | null;
  total_fills: number;
  last_trade_at: string | null;
  warning_codes: string[];
}

export interface StrategyDecision {
  signal: string;
  eligible: boolean;
  reason_codes: string[];
  analysis: Record<string, JsonValue>;
  occurred_at: string;
  decision_id: number;
  run_id: string;
  instance_id: string;
  symbol: string;
}

export interface EntryExecutionSettings {
  order_type: "market" | "limit";
  limit_price: string | null;
  limit_price_formula: string | null;
  time_in_force: TimeInForce;
  expires_after_minutes: number | null;
  cancellation_policy: "keep_open" | "cancel_on_expiry" | "cancel_on_signal_reset";
  partial_fill_behavior: "accept_partial" | "cancel_remainder" | "require_full_fill";
}

export interface ExitExecutionSettings {
  order_type: "market" | "limit";
  limit_offset_percentage: string | null;
  time_in_force: TimeInForce;
  maximum_wait_seconds: number;
  fallback_to_market: boolean;
}

export interface StrategyExecutionPlan {
  entry: EntryExecutionSettings;
  take_profit: ExitExecutionSettings;
  stop_loss: ExitExecutionSettings;
  strategy_exit: ExitExecutionSettings;
  manual_exit: ExitExecutionSettings;
}

export interface DcaSettings {
  enabled: boolean;
  maximum_entries: number;
  spacing_percentage: string;
  allocation_method: "equal" | "weighted" | "custom";
  custom_allocations: string[];
}

export interface StrategyRiskDefaults {
  requested_margin: string;
  requested_leverage: number;
  maximum_positions: number;
  maximum_exposure_percentage: string;
}

export interface StrategySetupDefaults {
  execution_plan: StrategyExecutionPlan;
  dca: DcaSettings;
  risk: StrategyRiskDefaults;
}

export interface StrategyTemplateCreate {
  type_id: string;
  name: string;
  description: string;
  timeframe_minutes: number;
  direction: "long" | "short" | "both";
  configuration: Record<string, JsonValue>;
  setup_defaults: StrategySetupDefaults;
  status: "draft" | "active";
}

export type StrategyTemplate = Omit<StrategyTemplateCreate, "status"> & {
  template_id: string;
  status: "draft" | "active" | "archived";
  current_revision: number;
  setup_count: number;
  created_at: string;
  updated_at: string;
  archived_at: string | null;
};

export interface StrategyTemplateVersion {
  version_id: number;
  template_id: string;
  revision: number;
  timeframe_minutes: number;
  direction: "long" | "short" | "both";
  configuration: Record<string, JsonValue>;
  setup_defaults: StrategySetupDefaults;
  created_at: string;
}

export type StrategyPresetCreate = StrategyTemplateCreate;

export type StrategyPreset = Omit<StrategyTemplate, "template_id"> & {
  preset_id: string;
  legacy_template_id: string;
};

export interface StrategyPresetVersion {
  version_id: number;
  preset_id: string;
  revision: number;
  timeframe_minutes: number;
  direction: "long" | "short" | "both";
  configuration: Record<string, JsonValue>;
  setup_defaults: StrategySetupDefaults;
  created_at: string;
}

export interface StrategyCoinSetupCreate {
  template_id: string;
  symbol: string;
  exchange?: string;
  market_type?: "usdt_perpetual";
  quote_currency?: string;
  timeframe_minutes?: number;
  direction?: "long" | "short" | "both";
  configuration_overrides?: Record<string, JsonValue>;
  setup_defaults_override?: StrategySetupDefaults | null;
  source_opportunity_id?: string | null;
}

export interface StrategyCoinSetup {
  setup_id: string;
  template_id: string;
  template_revision: number;
  runtime_instance_id: string | null;
  exchange: string;
  market_type: string;
  symbol: string;
  quote_currency: string;
  current_price: string | null;
  price_observed_at: string | null;
  price_state: "fresh" | "delayed" | "unavailable";
  timeframe_minutes: number;
  direction: "long" | "short" | "both";
  inherited_configuration: Record<string, JsonValue>;
  configuration_overrides: Record<string, JsonValue>;
  effective_configuration: Record<string, JsonValue>;
  inherited_setup_defaults: StrategySetupDefaults;
  setup_defaults_override: StrategySetupDefaults | null;
  effective_setup_defaults: StrategySetupDefaults;
  status:
    | "draft"
    | "ready_for_backtest"
    | "backtest_required"
    | "backtest_failed"
    | "backtest_passed"
    | "approved_paper"
    | "approved_testnet"
    | "approved_live"
    | "archived";
  latest_backtest_id: string | null;
  latest_backtest_revision: number | null;
  latest_backtest_assessment: "promising" | "mixed" | "weak" | "insufficient_data" | null;
  active_approval_mode: Environment | null;
  source_opportunity_id: string | null;
  revision: number;
  warnings: string[];
  created_at: string;
  updated_at: string;
  archived_at: string | null;
}

export interface StrategySetupApproval {
  approval_id: string;
  setup_id: string;
  setup_revision: number;
  mode: Environment;
  status: "approved" | "stale" | "revoked";
  note: string;
  approved_at: string;
  invalidated_at: string | null;
}

export interface StrategyOpportunity {
  opportunity_id: string;
  scan_id: string;
  strategy_type_id: string;
  strategy_version: string;
  timeframe_minutes: number;
  configuration: Record<string, JsonValue>;
  symbol: string;
  exchange: string;
  market_type: string;
  quote_currency: string;
  current_price: string | null;
  price_observed_at: string | null;
  price_state: "fresh" | "delayed" | "unavailable";
  scanner_score: number;
  signal: "long" | "short" | "none";
  eligible_now: boolean;
  qualifying_factors: string[];
  explanation_ar: string;
  warnings: string[];
  discovered_at: string;
  expires_at: string;
  status: "new" | "reviewed" | "approved" | "rejected" | "ignored" | "expired" | "converted";
  converted_setup_id: string | null;
}

export interface BotDeployment {
  deployment_id: string;
  setup_id: string;
  setup_revision: number;
  template_id: string;
  template_revision: number;
  runtime_instance_id: string;
  environment: Environment;
  strategy_type_id: string;
  strategy_version: string;
  configuration_snapshot: Record<string, JsonValue>;
  status: "not_started" | "starting" | "running" | "monitoring" | "paused" | "stopped" | "error";
  created_at: string;
  updated_at: string;
  started_at: string | null;
  ended_at: string | null;
  error_message: string | null;
}

export interface WorkflowSummary {
  templates: number;
  setups: number;
  opportunities_new: number;
  backtests_required: number;
  approvals_ready: number;
  deployments_running: number;
}

export interface PaperAccount {
  starting_balance: string;
  available_futures_balance: string;
  realized_pnl_total: string;
  fees_total: string;
  funding_total: string;
  net_pnl_total: string;
  position_quantity: string;
  pending_entry: boolean;
  protection_state: string;
  cooldown_until: string | null;
  risk_state: string;
  last_change_reason: string;
  revision: number;
}

export interface AccountRiskPolicy {
  daily_loss_enabled: boolean;
  daily_loss_limit: string;
  losing_trade_enabled: boolean;
  losing_trade_limit: number;
  automatic_trade_enabled: boolean;
  automatic_trade_limit: number;
  revision: number;
  updated_at: string;
}

export type AccountRiskLimitState =
  | "disabled"
  | "not_reached"
  | "reached"
  | "data_unavailable"
  | "synchronizing";

export interface AccountRiskLimitStatus {
  key: "daily_equity_loss" | "daily_losing_trades" | "daily_automatic_entries";
  enabled: boolean;
  state: AccountRiskLimitState;
  unit: "USDT" | "trades" | "entries";
  limit_value: string;
  used_value: string | null;
  remaining_value: string | null;
  blocks_manual_entries: boolean;
  blocks_automatic_entries: boolean;
}

export interface AccountRiskStatus {
  environment: "testnet" | "live";
  day: string;
  timezone: "Asia/Riyadh";
  synchronization_complete: boolean;
  risk_data_state: "ready" | "baseline_missing" | "account_data_unavailable" | "synchronizing";
  baseline_ready: boolean;
  baseline_equity: string | null;
  baseline_captured_at: string | null;
  current_equity: string | null;
  equity_loss_used: string;
  remaining_loss_allowance: string;
  losing_trades: number;
  automatic_trades: number;
  policy: AccountRiskPolicy;
  limits: AccountRiskLimitStatus[];
  manual_entries_blocked: boolean;
  automatic_entries_blocked: boolean;
  blocked_reason_codes: string[];
}

export interface PaperRisk {
  day: string;
  baseline_balance: string;
  realized_net_loss: string;
  losing_trades: number;
  automatic_fills: number;
  manual_entries_blocked: boolean;
  automatic_entries_blocked: boolean;
  cooldown_until: string | null;
  settings: {
    daily_loss_limit: string;
    losing_trade_limit: number;
    automatic_fill_limit: number;
    cooldown_seconds: number;
  };
}

export interface PaperPendingEntry {
  id: number;
  order_id: string | null;
  kind: "limit";
  direction: "long" | "short";
  quantity: string;
  allocated_margin: string;
  limit_price: string;
  leverage: number;
  entry_fee_rate: string;
  safety_reserve: string;
  expires_at: string;
  symbol: string | null;
  signal_zone: string | null;
  created_at: string;
  state: "pending";
}

export interface PaperPosition {
  direction: string;
  quantity: string;
  entry_price: string;
  entry_fee: string;
  allocated_margin: string;
  leverage: number;
  taker_fee_rate: string;
  maker_fee_rate: string;
  opened_at: string;
  symbol: string | null;
  managed_by_rangebot: boolean;
  origin: "manual" | "automatic_strategy" | "monitoring_conversion" | "legacy_automatic" | null;
  instance_id: string | null;
  run_id: string | null;
  strategy_name: string | null;
  ownership_created_at: string | null;
  trailing_stop_price: string | null;
  trailing_stop_distance: string | null;
  trailing_state: "desired" | "active" | "error" | null;
  trailing_order_id: string | null;
  trailing_last_error: string | null;
}

export interface WatchlistItem {
  symbol: string;
  priority: number;
  is_active: boolean;
  monitoring_only: boolean;
  direction: "long_only" | "short_only" | "both";
  last_price: string | null;
}

export interface PaperWatchlist {
  items: WatchlistItem[];
  automatic_trading_enabled: boolean;
}

export interface AccountEquityPoint {
  point_id: number;
  mode: "paper" | "testnet" | "live";
  occurred_at: string;
  total_equity: string;
  available_balance: string;
  used_margin: string;
  margin_usage_percentage: string;
  realized_pnl_total: string;
  unrealized_pnl: string;
  fees_total: string;
  funding_total: string;
  net_pnl_total: string;
  open_exposure: string;
}

export interface AccountPerformanceSeries {
  mode: "paper" | "testnet" | "live";
  period: "today" | "7d" | "30d" | "all";
  generated_at: string;
  points: AccountEquityPoint[];
  baseline_equity: string | null;
  ending_equity: string | null;
  equity_change: string | null;
  equity_change_percentage: string | null;
  maximum_drawdown_percentage: string | null;
  realized_pnl_total: string | null;
  unrealized_pnl: string | null;
  fees_total: string | null;
  funding_total: string | null;
  net_pnl_total: string | null;
  open_exposure: string | null;
}

export interface ActivityEvent {
  event_id: string;
  occurred_at: string;
  category:
    | "decision"
    | "strategy"
    | "order"
    | "paper"
    | "risk"
    | "system"
    | "connection"
    | "research";
  severity: "neutral" | "positive" | "warning" | "negative";
  title_ar: string;
  detail_ar: string;
  environment: "paper" | "testnet" | "live" | null;
  symbol: string | null;
  strategy_instance_id: string | null;
  strategy_name: string | null;
  status: string | null;
  source_identity: string | null;
}

export interface PrivateStreamState {
  mode: "testnet" | "live" | null;
  status:
    | "disabled"
    | "credentials_missing"
    | "connecting"
    | "connected"
    | "reconciling"
    | "reconnecting"
    | "error";
  connected: boolean;
  subscribed_channels: string[];
  last_event_at: string | null;
  last_reconciled_at: string | null;
  last_error: string | null;
  revision: number;
}

export interface DashboardBundle {
  runtime: RemoteData<RuntimeState>;
  settings: RemoteData<ApplicationSettings>;
  strategyTypes: RemoteData<StrategyTypeMetadata[]>;
  strategies: RemoteData<StrategyInstance[]>;
  strategyOverview: RemoteData<StrategyOverviewItem[]>;
  liveState: RemoteData<ModeState>;
  testnetState: RemoteData<ModeState>;
  liveRisk: RemoteData<AccountRiskStatus>;
  testnetRisk: RemoteData<AccountRiskStatus>;
  privateStream: RemoteData<PrivateStreamState>;
  paperAccount: RemoteData<PaperAccount>;
  paperPerformance: RemoteData<AccountPerformanceSeries>;
  paperRisk: RemoteData<PaperRisk>;
  paperPosition: RemoteData<PaperPosition | null>;
  paperPendingEntry: RemoteData<PaperPendingEntry | null>;
  watchlist: RemoteData<PaperWatchlist>;
  activity: RemoteData<ActivityEvent[]>;
  loadedAt: string;
}

export type OrderType = "market" | "limit";
export type OrderSizeMode = "quantity" | "margin" | "balance_percentage";
export type TimeInForce = "gtc" | "ioc" | "poc" | "fok";

export interface ManualOrderRequest {
  environment: Environment;
  symbol: string;
  direction: "long" | "short";
  order_type: OrderType;
  size_mode: OrderSizeMode;
  quantity?: string;
  margin_amount?: string;
  balance_percentage?: string;
  leverage: number;
  limit_price?: string;
  time_in_force: TimeInForce;
  expires_at?: string;
}

export interface OrderValidationIssue {
  code: string;
  message_ar: string;
  field: string | null;
}

export interface ManualOrderPreview {
  request: ManualOrderRequest;
  generated_at: string;
  last_price: string;
  mark_price: string | null;
  best_bid: string | null;
  best_ask: string | null;
  market_data_state: string;
  market_observed_at: string;
  available_balance: string;
  contract_multiplier: string;
  quantity_step: string;
  minimum_quantity: string;
  minimum_notional: string;
  approximate_minimum_margin: string;
  maximum_leverage: number;
  estimated_quantity: string;
  estimated_notional: string;
  estimated_margin: string;
  estimated_opening_fee: string;
  estimated_fee_rate: string;
  estimated_take_profit_price: string | null;
  estimated_stop_loss_price: string | null;
  estimated_liquidation_price: string | null;
  reference_price: string;
  limit_distance_percentage: string | null;
  estimated_liquidity_behavior: "maker" | "taker" | "unknown";
  supported_time_in_force: TimeInForce[];
  validation_issues: OrderValidationIssue[];
  can_submit: boolean;
  uses_real_funds: boolean;
  live_warning_ar: string | null;
  safety_fingerprint: string;
}

export interface ManualOrderResult {
  accepted: boolean;
  environment: Environment;
  origin: "manual";
  client_request_id: string;
  order_id: string | null;
  message_ar: string;
  preview: ManualOrderPreview;
}
