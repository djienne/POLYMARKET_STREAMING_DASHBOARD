"""Central registry of collector instances and derived snapshots.

Exposed to routes so both HTTP + WS can build the same payloads.
"""
from __future__ import annotations

import csv
import time
from typing import Optional

from ..collector.calibration_watcher import CalibrationWatcher
from ..collector.docker_log_tail import DockerLogTail
from ..collector.leaderboard_reader import LeaderboardReader
from ..collector.liveness import current_liveness
from ..collector.orderbook_tail import OrderbookTail
from ..collector.polymarket_client import PolymarketClient
from ..collector.state_reader import (
    STARTING_CAPITAL,
    StateReader,
    _is_meaningful_live_close_values,
)
from ..collector.terminal_reader import TerminalReader
from ..collector.trades_tail import TradesTail
from ..config import settings
from ..derive.edge import compute_edge
from ..derive.equity import equity_curve, equity_timeseries
from ..derive.window import compute_window
from datetime import datetime, timezone

from ..models import (
    BootstrapPayload,
    ChartMarker,
    EdgeRatio,
    InstanceStats,
    LivenessInfo,
    PositionState,
    SharedConfig,
    TerminalSnapshot,
    TodaySummary,
    WindowState,
)
from ..time_utils import PARIS_TZ, iso_to_unix, paris_date_key, paris_day_start_utc


def _model_series_for_chart(hub: "Hub", side: str) -> list[dict]:
    if settings.mode == "live":
        return hub.terminal.model_series(side)
    return hub.docker_log.model_series(side) or hub.terminal.model_series(side)


class Hub:
    def __init__(self) -> None:
        self.terminal = TerminalReader(settings.terminal_path())
        self.state = StateReader(
            path_fn=lambda: settings.state_snapshot_path() if settings.mode == "dry_run"
            else settings.live_state_path()
        )
        self.trades = TradesTail(path_fn=lambda: settings.trades_path())
        self.leaderboard = LeaderboardReader(path_fn=lambda: settings.leaderboard_path())
        self.orderbook = OrderbookTail(path_fn=lambda: settings.orderbook_path())
        self.docker_log = DockerLogTail(
            container=settings.docker_container,
            slug_fn=lambda: self._current_slug(),
        )
        self.polymarket = PolymarketClient(slug_fn=lambda: self._current_slug())
        self.calibration = CalibrationWatcher(
            log_paths=settings.trader_log_paths(),
            terminal_reader=self.terminal,
        )
        self._shared_cfg_cache: Optional[SharedConfig] = None
        self._shared_cfg_mtime: Optional[float] = None

    def _current_slug(self) -> Optional[str]:
        """Resolve the current 15-min market slug from the freshest available signal."""
        # Refresh state so we can look for any active open position
        self.state.read_if_changed()
        self.terminal.read_if_changed()

        # 1. Terminal JSON (rare but accurate)
        term = self.terminal.latest
        slug = term.market.slug if term and term.market else None

        # 2. Any instance with an open position is by definition trading the active market
        if not slug:
            for inst in (self.state.raw.get("instances") or {}).values():
                pos = inst.get("position")
                if pos and pos.get("market_id"):
                    slug = pos["market_id"]
                    break

        # 3. Fallback: current quarter-hour boundary.
        import re
        import time as _t
        now = int(_t.time())
        m = re.search(r"btc-updown-15m-(\d+)", slug or "")
        if not slug or not m or (int(m.group(1)) + 900) < now:
            slug = f"btc-updown-15m-{(now // 900) * 900}"
        return slug

    def shared_config(self) -> SharedConfig:
        import json
        path = settings.grid_config_path() if settings.mode == "dry_run" else settings.live_config_path()
        try:
            mtime = path.stat().st_mtime
        except FileNotFoundError:
            return self._shared_cfg_cache or SharedConfig()
        if self._shared_cfg_mtime == mtime and self._shared_cfg_cache is not None:
            return self._shared_cfg_cache
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return SharedConfig()
        cfg = SharedConfig(
            starting_capital=raw.get("starting_capital"),
            order_size_pct=raw.get("order_size_pct"),
            friction_pct=raw.get("friction_pct"),
            max_entry_price=raw.get("max_entry_price"),
            no_trade_first_s=raw.get("no_trade_first_seconds"),
            no_trade_last_s=raw.get("no_trade_last_seconds"),
            grace_period_s=raw.get("grace_period_seconds"),
            liquidity_mode=raw.get("liquidity_mode"),
            alpha_up=raw.get("edge_alpha_up"),
            alpha_down=raw.get("edge_alpha_down"),
            floor_up=raw.get("edge_floor_up"),
            floor_down=raw.get("edge_floor_down"),
            tp_pct=raw.get("tp_percentage"),
            sl_pct=raw.get("stop_loss_pct"),
        )
        self._shared_cfg_cache = cfg
        self._shared_cfg_mtime = mtime
        return cfg

    def starting_capital(self) -> float:
        capital = self.state.raw.get("capital")
        if isinstance(capital, dict):
            live_starting = capital.get("starting")
            try:
                return float(live_starting)
            except (TypeError, ValueError):
                pass
        configured = self.shared_config().starting_capital
        if configured is None:
            return STARTING_CAPITAL
        try:
            return float(configured)
        except (TypeError, ValueError):
            return STARTING_CAPITAL

    @staticmethod
    def _apply_leaderboard_context(
        instance: Optional[InstanceStats],
        lb_row,
    ) -> Optional[InstanceStats]:
        if instance is None or lb_row is None:
            return instance
        instance.rank = lb_row.rank
        instance.params = lb_row.params
        instance.sharpe = lb_row.sharpe
        instance.max_drawdown = lb_row.max_drawdown
        instance.max_drawdown_pct = lb_row.max_drawdown_pct
        instance.wins = lb_row.wins
        instance.losses = lb_row.losses
        instance.win_rate = lb_row.win_rate
        instance.trades_count = lb_row.trades
        return instance

    def instance_snapshot(self, instance_id: int):
        shared_cfg = self.shared_config()
        starting_capital = self.starting_capital()
        lb_row = self.leaderboard.row(instance_id) if settings.mode == "dry_run" else None
        instance = self.state.instance(instance_id, starting_capital=starting_capital)
        instance = self._apply_leaderboard_context(instance, lb_row)
        position = self._position_with_grace(
            self.state.position(instance_id),
            shared_cfg.grace_period_s,
        )
        pnls = self.state.trade_pnls(instance_id)
        equity = equity_curve(pnls, starting_capital=starting_capital)
        equity_series = equity_timeseries(
            self.trades.realized_history(instance_id), starting_capital=starting_capital
        )
        today_summary = self._today_summary(
            instance_id,
            starting_capital,
            instance.capital if instance is not None else starting_capital,
        )
        return instance, position, equity, equity_series, today_summary

    def build_bootstrap(self, instance_id: int) -> BootstrapPayload:
        # Force refresh
        self.state.read_if_changed()
        self.terminal.read_if_changed()
        self.leaderboard.read_if_changed()
        self.orderbook.poll()
        slug = self._current_slug()
        shared_cfg = self.shared_config()

        instance, position, equity, equity_series, today_summary = self.instance_snapshot(instance_id)
        lb_row = self.leaderboard.row(instance_id) if settings.mode == "dry_run" else None

        terminal = self.terminal.latest or TerminalSnapshot()
        # Polymarket prices: direct CLOB API (primary) → orderbook CSV fallback for paper mode.
        price_source = self.polymarket.latest or self.orderbook.latest
        if price_source is not None:
            terminal.polymarket = price_source

        # Tell the terminal reader to reset its model-probability history on new market
        self.terminal.reset_history_if_new_slug(slug)
        if terminal.market is not None and not terminal.market.slug:
            terminal.market.slug = slug
            import re
            m = re.search(r"btc-updown-15m-(\d+)", slug)
            if m:
                start = int(m.group(1))
                terminal.market.window_start_unix = start
                terminal.market.window_end_unix = start + 900
        window = compute_window(
            slug,
            no_trade_first_s=(
                shared_cfg.no_trade_first_s
                if shared_cfg.no_trade_first_s is not None
                else 300.0
            ),
            no_trade_last_s=(
                shared_cfg.no_trade_last_s
                if shared_cfg.no_trade_last_s is not None
                else 120.0
            ),
        )

        trades = self.trades.recent(instance_id, n=50)

        liveness = current_liveness()

        edge_up, edge_down = self._edges_from(terminal, lb_row)

        return BootstrapPayload(
            mode=settings.mode,
            instance=instance,
            position=position,
            terminal=terminal,
            window=window,
            trades=trades,
            equity=equity,
            leaderboard_top=self.leaderboard.top(15),
            liveness=liveness,
            calibration=self.calibration.status,
            edge_up=edge_up,
            edge_down=edge_down,
            shared_config=shared_cfg,
            today_summary=today_summary,
            series_up=self._scope_series(
                self.polymarket.series("UP") or self.orderbook.series("UP"), slug
            ),
            series_down=self._scope_series(
                self.polymarket.series("DOWN") or self.orderbook.series("DOWN"), slug
            ),
            model_up=self._scope_series(
                _model_series_for_chart(self, "UP"), slug
            ),
            model_down=self._scope_series(
                _model_series_for_chart(self, "DOWN"), slug
            ),
            markers=self._markers_for(instance_id, slug),
            window_start_iso=_window_iso(slug, 0),
            window_end_iso=_window_iso(slug, 900),
            equity_series=equity_series,
        )

    def _edges_from(self, terminal: TerminalSnapshot, lb_row) -> tuple[Optional["EdgeRatio"], Optional["EdgeRatio"]]:
        if not terminal.probabilities:
            return None, None
        if lb_row is not None:
            params = lb_row.params
        else:
            cfg = self.shared_config()
            if (
                cfg.alpha_up is None or
                cfg.alpha_down is None or
                cfg.floor_up is None or
                cfg.floor_down is None
            ):
                return None, None
            class _Params:
                alpha_up = cfg.alpha_up
                alpha_down = cfg.alpha_down
                floor_up = cfg.floor_up
                floor_down = cfg.floor_down
            params = _Params()
        model_up = (
            terminal.probabilities.avg_above
            or terminal.probabilities.mc_above
            or terminal.probabilities.ssvi_surface_above
        )
        model_down = (
            terminal.probabilities.avg_below
            or terminal.probabilities.mc_below
            or terminal.probabilities.ssvi_surface_below
        )
        market_up = terminal.polymarket.prob_up if terminal.polymarket else None
        market_down = terminal.polymarket.prob_down if terminal.polymarket else None
        return (
            compute_edge("UP", model_up, market_up, params.alpha_up, params.floor_up),
            compute_edge("DOWN", model_down, market_down, params.alpha_down, params.floor_down),
        )

    def current_edges(self, instance_id: int) -> tuple[Optional["EdgeRatio"], Optional["EdgeRatio"]]:
        """Compute live edges from current terminal/polymarket state for the given instance."""
        terminal = self.terminal.latest or TerminalSnapshot()
        price_source = self.polymarket.latest or self.orderbook.latest
        if price_source is not None:
            terminal.polymarket = price_source
        lb_row = self.leaderboard.row(instance_id) if settings.mode == "dry_run" else None
        return self._edges_from(terminal, lb_row)

    @staticmethod
    def _grace_remaining(
        last_exit_at: Optional[str],
        grace_period_s: Optional[float],
        now_unix: Optional[float] = None,
    ) -> Optional[float]:
        if last_exit_at is None or grace_period_s is None or grace_period_s <= 0:
            return None
        exited_at = iso_to_unix(last_exit_at)
        if exited_at is None:
            return None
        if now_unix is None:
            now_unix = time.time()
        remaining = grace_period_s - (now_unix - exited_at)
        return max(0.0, remaining)

    @classmethod
    def _position_with_grace(
        cls,
        position: PositionState,
        grace_period_s: Optional[float],
    ) -> PositionState:
        if position.open is not None:
            position.grace_remaining_s = None
            return position
        position.grace_remaining_s = cls._grace_remaining(
            position.last_exit_at,
            grace_period_s,
        )
        return position

    @staticmethod
    def _today_pnl_pct(
        summary: TodaySummary,
        history,
        starting_capital: float,
        current_capital: float,
        day_key: str,
    ) -> Optional[float]:
        if summary.closed <= 0:
            return None
        day_start = paris_day_start_utc(day_key)
        base_capital: Optional[float] = None
        if day_start is not None:
            for ev in reversed(history):
                ts = iso_to_unix(getattr(ev, "timestamp", None))
                if ts is None or ts >= day_start.timestamp():
                    continue
                capital = getattr(ev, "capital", None)
                if capital is not None:
                    try:
                        base_capital = float(capital)
                    except (TypeError, ValueError):
                        base_capital = None
                    break
        if base_capital is None:
            fallback = current_capital - summary.pnl
            base_capital = fallback if fallback > 0 else starting_capital
        if base_capital <= 0:
            return None
        return (summary.pnl / base_capital) * 100.0

    def _live_today_summary(
        self,
        day_key: str,
        starting_capital: float,
        current_capital: float,
    ) -> TodaySummary:
        summary = TodaySummary()
        base_capital: Optional[float] = None
        equity_path = settings.resolved_results_dir / "15m_live_equity.csv"
        trades_path = settings.trades_path()
        day_start = paris_day_start_utc(day_key)
        if trades_path.exists():
            try:
                with trades_path.open("r", encoding="utf-8", newline="") as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        try:
                            pnl = row.get("pnl")
                            cost_basis = row.get("cost_basis")
                            proceeds = row.get("proceeds")
                            meaningful = _is_meaningful_live_close_values(
                                pnl,
                                cost_basis,
                                proceeds,
                            )
                        except (TypeError, ValueError):
                            meaningful = False
                        if not meaningful:
                            continue
                        if paris_date_key(row.get("opened_at")) == day_key:
                            summary.entries += 1
                        if paris_date_key(row.get("closed_at")) != day_key:
                            continue
                        summary.closed += 1
                        try:
                            summary.pnl += float(pnl) if pnl not in (None, "") else 0.0
                        except (TypeError, ValueError):
                            pass
                        result = row.get("result")
                        if result in {"TP_FILLED", "WIN_EXPIRY"}:
                            summary.wins += 1
                        elif result in {"STOP_LOSS", "LOSS_EXPIRY"}:
                            summary.losses += 1
            except OSError:
                pass
        for pos in self.state.raw.get("open_positions") or []:
            if not isinstance(pos, dict):
                continue
            if paris_date_key(pos.get("opened_at")) == day_key:
                summary.entries += 1
        if equity_path.exists():
            try:
                with equity_path.open("r", encoding="utf-8", newline="") as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        ts = iso_to_unix(row.get("timestamp"))
                        if ts is None:
                            continue
                        if day_start is not None and ts < day_start.timestamp():
                            for key in ("equity", "capital"):
                                val = row.get(key)
                                if val in (None, ""):
                                    continue
                                try:
                                    base_capital = float(val)
                                except (TypeError, ValueError):
                                    pass
                                else:
                                    break
                            continue
            except OSError:
                pass
        if base_capital is None and summary.closed > 0:
            fallback = current_capital - summary.pnl
            base_capital = fallback if fallback > 0 else starting_capital
        summary.pnl_pct = (
            (summary.pnl / base_capital) * 100.0
            if base_capital is not None and base_capital > 0 and summary.closed > 0
            else None
        )
        return summary

    def _today_summary(
        self,
        instance_id: int,
        starting_capital: float,
        current_capital: float,
    ) -> TodaySummary:
        day_key = paris_date_key(dt=datetime.now(timezone.utc))
        if settings.mode == "live":
            return self._live_today_summary(day_key, starting_capital, current_capital)
        summary = self.trades.today_summary(instance_id, day_key)
        summary.pnl_pct = self._today_pnl_pct(
            summary,
            self.trades.realized_history(instance_id),
            starting_capital,
            current_capital,
            day_key,
        )
        return summary

    @staticmethod
    def _window_bounds(slug: Optional[str]) -> Optional[tuple[int, int]]:
        if not slug:
            return None
        import re
        m = re.search(r"btc-updown-15m-(\d+)", slug)
        if not m:
            return None
        start = int(m.group(1))
        return start, start + 900

    @classmethod
    def _scope_series(cls, rows: list, slug: Optional[str]) -> list:
        bounds = cls._window_bounds(slug)
        if not bounds:
            return rows
        start, end = bounds
        out = []
        for p in rows:
            t = p["t"] if isinstance(p, dict) else p.t
            ts = iso_to_unix(t)
            if ts is None:
                continue
            if start <= ts <= end:
                out.append(p)
        return out

    def _markers_for(self, instance_id: int, slug: Optional[str]) -> list[ChartMarker]:
        bounds = self._window_bounds(slug)
        if not bounds:
            return []
        start, end = bounds
        out: list[ChartMarker] = []
        for ev in self.trades.recent(instance_id, n=200):
            if ev.market_id and ev.market_id != slug:
                continue
            ts = iso_to_unix(ev.timestamp)
            if ts is None:
                continue
            if not (start <= ts <= end):
                continue
            kind = None
            if ev.event == "ENTRY":
                kind = "ENTRY"
            elif ev.event in ("TP_FILLED", "WIN_EXPIRY"):
                kind = "WIN"
            elif ev.event in ("STOP_LOSS", "LOSS_EXPIRY"):
                kind = "LOSS"
            if kind is None:
                continue
            price = ev.entry_price if kind == "ENTRY" else ev.exit_price
            out.append(
                ChartMarker(
                    t=ev.timestamp,
                    kind=kind,  # type: ignore[arg-type]
                    side=(ev.direction if ev.direction in ("UP", "DOWN") else None),
                    price=price,
                    pnl=ev.pnl,
                )
            )
        return out


def _window_iso(slug: Optional[str], offset: int) -> Optional[str]:
    if not slug:
        return None
    import re
    m = re.search(r"btc-updown-15m-(\d+)", slug)
    if not m:
        return None
    ts = int(m.group(1)) + offset
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()


hub: Optional[Hub] = None


def get_hub() -> Hub:
    global hub
    if hub is None:
        hub = Hub()
    return hub
