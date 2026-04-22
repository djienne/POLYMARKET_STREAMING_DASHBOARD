from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field


class InstanceParams(BaseModel):
    alpha_up: float
    alpha_down: float
    floor_up: float
    floor_down: float
    tp_pct: float
    sl_pct: float


class LeaderboardRow(BaseModel):
    rank: int
    instance_id: int
    total_pnl: float
    sharpe: float
    max_drawdown: float
    max_drawdown_pct: float
    wins: int
    losses: int
    win_rate: float
    trades: int
    params: InstanceParams
    liquidity_mode: str


class InstanceStats(BaseModel):
    instance_id: int
    rank: Optional[int] = None
    capital: float
    starting_capital: float
    total_pnl: float
    total_pnl_pct: float
    sharpe: float
    max_drawdown: float
    max_drawdown_pct: float
    wins: int
    losses: int
    win_rate: float
    trades_count: int
    params: Optional[InstanceParams] = None


class OpenPosition(BaseModel):
    direction: Literal["UP", "DOWN"]
    entry_price: float
    shares: float
    tp_target: Optional[float] = None
    sl_target: Optional[float] = None
    entered_at: Optional[str] = None
    market_id: Optional[str] = None
    notional: Optional[float] = None


class PositionState(BaseModel):
    open: Optional[OpenPosition] = None
    last_exit_at: Optional[str] = None
    grace_remaining_s: Optional[float] = None


class ProbabilityBundle(BaseModel):
    # All optional because some models may not run
    ssvi_surface_above: Optional[float] = None
    ssvi_surface_below: Optional[float] = None
    mc_above: Optional[float] = None
    mc_below: Optional[float] = None
    heston_above: Optional[float] = None
    heston_below: Optional[float] = None
    bl_above: Optional[float] = None
    bl_below: Optional[float] = None
    avg_above: Optional[float] = None
    avg_below: Optional[float] = None
    bl_mc_divergence: Optional[float] = None
    preferred_model: Optional[str] = None


class MarketInfo(BaseModel):
    slug: Optional[str] = None
    title: Optional[str] = None
    window_start_unix: Optional[int] = None
    window_end_unix: Optional[int] = None
    spot_price: Optional[float] = None
    barrier: Optional[float] = None
    direction: Optional[str] = None
    ttm_days: Optional[float] = None
    ttm_seconds: Optional[float] = None


class PolymarketPrices(BaseModel):
    best_bid: Optional[float] = None
    best_ask: Optional[float] = None
    mid: Optional[float] = None
    prob_up: Optional[float] = None
    prob_down: Optional[float] = None


class TimingInfo(BaseModel):
    calibration_s: Optional[float] = None
    surface_fit_s: Optional[float] = None
    mc_s: Optional[float] = None
    bl_s: Optional[float] = None
    surface_bl_s: Optional[float] = None


class TerminalSnapshot(BaseModel):
    timestamp: Optional[str] = None
    market: MarketInfo = MarketInfo()
    probabilities: ProbabilityBundle = ProbabilityBundle()
    polymarket: PolymarketPrices = PolymarketPrices()
    timing: TimingInfo = TimingInfo()
    age_seconds: Optional[float] = None


class WindowState(BaseModel):
    elapsed_s: float
    total_s: float = 900.0
    no_trade_first_s: float = 300.0
    no_trade_last_s: float = 120.0
    zone: Literal["blocked_first", "tradeable", "blocked_last", "expired", "unknown"]
    slug: Optional[str] = None


class TradeEvent(BaseModel):
    instance_id: int
    timestamp: str
    event: str
    direction: Optional[str] = None
    market_id: Optional[str] = None
    entry_price: Optional[float] = None
    exit_price: Optional[float] = None
    shares: Optional[float] = None
    pnl: Optional[float] = None
    pnl_pct: Optional[float] = None
    capital: Optional[float] = None
    model_prob: Optional[float] = None
    poly_prob: Optional[float] = None
    spot_price: Optional[float] = None
    barrier: Optional[float] = None


class EdgeRatio(BaseModel):
    side: Literal["UP", "DOWN"]
    market_prob: Optional[float] = None
    model_prob: Optional[float] = None
    required_prob: Optional[float] = None
    current_ratio: Optional[float] = None
    required_ratio: Optional[float] = None
    margin: Optional[float] = None
    has_edge: Optional[bool] = None


class CalibrationStatus(BaseModel):
    active: bool = False
    started_at: Optional[str] = None
    elapsed_s: Optional[float] = None
    last_timing: Optional[TimingInfo] = None


class LivenessInfo(BaseModel):
    bot_live: bool
    lock_exists: bool
    terminal_age_s: Optional[float] = None
    last_terminal_ts: Optional[str] = None
    cpu_pct: Optional[float] = None
    # Live-trader execution location + latency to Polymarket from that side.
    # execution_location is "local" | "vps" | "stopped" | null (unknown).
    # polymarket_ping_ms reflects the ACTIVE side (local measures from the
    # dashboard host; vps measures via ssh-to-VPS + curl so the number is
    # what the VPS trader actually experiences).
    execution_location: Optional[str] = None
    execution_label: Optional[str] = None  # human-friendly, e.g. "VPS Tokyo"
    polymarket_ping_ms: Optional[float] = None
    polymarket_ping_age_s: Optional[float] = None


class SharedConfig(BaseModel):
    starting_capital: Optional[float] = None
    order_size_pct: Optional[float] = None
    friction_pct: Optional[float] = None
    max_entry_price: Optional[float] = None
    no_trade_first_s: Optional[float] = None
    no_trade_last_s: Optional[float] = None
    grace_period_s: Optional[float] = None
    liquidity_mode: Optional[str] = None
    alpha_up: Optional[float] = None
    alpha_down: Optional[float] = None
    floor_up: Optional[float] = None
    floor_down: Optional[float] = None
    tp_pct: Optional[float] = None
    sl_pct: Optional[float] = None


class TodaySummary(BaseModel):
    pnl: float = 0.0
    pnl_pct: Optional[float] = None
    entries: int = 0
    wins: int = 0
    losses: int = 0
    closed: int = 0


class PricePoint(BaseModel):
    t: str
    v: float


class ChartMarker(BaseModel):
    t: str
    kind: Literal["ENTRY", "WIN", "LOSS"]
    side: Optional[Literal["UP", "DOWN"]] = None
    price: Optional[float] = None
    pnl: Optional[float] = None


class BootstrapPayload(BaseModel):
    mode: str
    instance: Optional[InstanceStats] = None
    position: PositionState = PositionState()
    terminal: TerminalSnapshot = TerminalSnapshot()
    window: Optional[WindowState] = None
    trades: list[TradeEvent] = []
    equity: list[float] = []
    leaderboard_top: list[LeaderboardRow] = []
    liveness: LivenessInfo
    calibration: CalibrationStatus = CalibrationStatus()
    edge_up: Optional[EdgeRatio] = None
    edge_down: Optional[EdgeRatio] = None
    shared_config: SharedConfig = SharedConfig()
    today_summary: TodaySummary = TodaySummary()
    series_up: list[PricePoint] = []
    series_down: list[PricePoint] = []
    model_up: list[PricePoint] = []
    model_down: list[PricePoint] = []
    markers: list[ChartMarker] = []
    window_start_iso: Optional[str] = None
    window_end_iso: Optional[str] = None
    equity_series: list[PricePoint] = []


class WsEnvelope(BaseModel):
    type: str
    id: str
    server_time: str
    data: dict
