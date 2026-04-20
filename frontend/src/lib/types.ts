export interface InstanceParams {
  alpha_up: number;
  alpha_down: number;
  floor_up: number;
  floor_down: number;
  tp_pct: number;
  sl_pct: number;
}

export interface LeaderboardRow {
  rank: number;
  instance_id: number;
  total_pnl: number;
  sharpe: number;
  max_drawdown: number;
  max_drawdown_pct: number;
  wins: number;
  losses: number;
  win_rate: number;
  trades: number;
  params: InstanceParams;
  liquidity_mode: string;
}

export interface InstanceStats {
  instance_id: number;
  rank?: number | null;
  capital: number;
  starting_capital: number;
  total_pnl: number;
  total_pnl_pct: number;
  sharpe: number;
  max_drawdown: number;
  max_drawdown_pct: number;
  wins: number;
  losses: number;
  win_rate: number;
  trades_count: number;
  params?: InstanceParams | null;
}

export interface OpenPosition {
  direction: "UP" | "DOWN";
  entry_price: number;
  shares: number;
  tp_target?: number | null;
  sl_target?: number | null;
  entered_at?: string | null;
  market_id?: string | null;
  notional?: number | null;
}

export interface PositionState {
  open: OpenPosition | null;
  last_exit_at?: string | null;
  grace_remaining_s?: number | null;
}

export interface ProbabilityBundle {
  ssvi_surface_above: number | null;
  ssvi_surface_below: number | null;
  mc_above: number | null;
  mc_below: number | null;
  heston_above: number | null;
  heston_below: number | null;
  bl_above: number | null;
  bl_below: number | null;
  avg_above: number | null;
  avg_below: number | null;
  bl_mc_divergence: number | null;
  preferred_model: string | null;
}

export interface MarketInfo {
  slug: string | null;
  title: string | null;
  window_start_unix: number | null;
  window_end_unix: number | null;
  spot_price: number | null;
  barrier: number | null;
  direction: string | null;
  ttm_days: number | null;
  ttm_seconds: number | null;
}

export interface PolymarketPrices {
  best_bid: number | null;
  best_ask: number | null;
  mid: number | null;
  prob_up: number | null;
  prob_down: number | null;
}

export interface TimingInfo {
  calibration_s: number | null;
  surface_fit_s: number | null;
  mc_s: number | null;
  bl_s: number | null;
  surface_bl_s: number | null;
}

export interface TerminalSnapshot {
  timestamp: string | null;
  market: MarketInfo;
  probabilities: ProbabilityBundle;
  polymarket: PolymarketPrices;
  timing: TimingInfo;
  age_seconds: number | null;
}

export type WindowZone =
  | "blocked_first"
  | "tradeable"
  | "blocked_last"
  | "expired"
  | "unknown";

export interface WindowState {
  elapsed_s: number;
  total_s: number;
  no_trade_first_s: number;
  no_trade_last_s: number;
  zone: WindowZone;
  slug: string | null;
}

export interface TradeEvent {
  instance_id: number;
  timestamp: string;
  event: string;
  direction?: string | null;
  market_id?: string | null;
  entry_price?: number | null;
  exit_price?: number | null;
  shares?: number | null;
  pnl?: number | null;
  pnl_pct?: number | null;
  capital?: number | null;
  model_prob?: number | null;
  poly_prob?: number | null;
  spot_price?: number | null;
  barrier?: number | null;
}

export interface EdgeRatio {
  side: "UP" | "DOWN";
  market_prob: number | null;
  model_prob: number | null;
  required_prob: number | null;
  current_ratio: number | null;
  required_ratio: number | null;
  margin: number | null;
  has_edge: boolean | null;
}

export interface CalibrationStatus {
  active: boolean;
  started_at: string | null;
  elapsed_s: number | null;
  last_timing: TimingInfo | null;
}

export interface LivenessInfo {
  bot_live: boolean;
  lock_exists: boolean;
  terminal_age_s: number | null;
  last_terminal_ts: string | null;
}

export interface SharedConfig {
  starting_capital: number | null;
  order_size_pct: number | null;
  friction_pct: number | null;
  max_entry_price: number | null;
  no_trade_first_s: number | null;
  no_trade_last_s: number | null;
  grace_period_s: number | null;
  liquidity_mode: string | null;
}

export interface PricePoint {
  t: string; // ISO timestamp
  v: number; // 0..1 mid probability
}

export interface ChartMarker {
  t: string;
  kind: "ENTRY" | "WIN" | "LOSS";
  side?: "UP" | "DOWN" | null;
  price?: number | null;
  pnl?: number | null;
}

export interface BootstrapPayload {
  mode: string;
  instance: InstanceStats | null;
  position: PositionState;
  terminal: TerminalSnapshot;
  window: WindowState | null;
  trades: TradeEvent[];
  equity: number[];
  leaderboard_top: LeaderboardRow[];
  liveness: LivenessInfo;
  calibration: CalibrationStatus;
  edge_up: EdgeRatio | null;
  edge_down: EdgeRatio | null;
  shared_config: SharedConfig;
  series_up: PricePoint[];
  series_down: PricePoint[];
  model_up: PricePoint[];
  model_down: PricePoint[];
  markers: ChartMarker[];
  window_start_iso: string | null;
  window_end_iso: string | null;
  equity_series: PricePoint[];
}

export interface WsEnvelope<T = unknown> {
  type: string;
  id: string;
  server_time: string;
  data: T;
}
