"""Central registry of collector instances and derived snapshots.

Exposed to routes so both HTTP + WS can build the same payloads.
"""
from __future__ import annotations

import time
from typing import Optional

from ..collector.calibration_watcher import CalibrationWatcher
from ..collector.docker_log_tail import DockerLogTail
from ..collector.leaderboard_reader import LeaderboardReader
from ..collector.liveness import current_liveness
from ..collector.orderbook_tail import OrderbookTail
from ..collector.polymarket_client import PolymarketClient
from ..collector.state_reader import STARTING_CAPITAL, StateReader
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
    WindowState,
)
from ..time_utils import iso_to_unix


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
        starting_capital = self.starting_capital()
        lb_row = self.leaderboard.row(instance_id) if settings.mode == "dry_run" else None
        instance = self.state.instance(instance_id, starting_capital=starting_capital)
        instance = self._apply_leaderboard_context(instance, lb_row)
        position = self.state.position(instance_id)
        pnls = self.state.trade_pnls(instance_id)
        equity = equity_curve(pnls, starting_capital=starting_capital)
        equity_series = equity_timeseries(
            self.trades.realized_history(instance_id), starting_capital=starting_capital
        )
        return instance, position, equity, equity_series

    def build_bootstrap(self, instance_id: int) -> BootstrapPayload:
        # Force refresh
        self.state.read_if_changed()
        self.terminal.read_if_changed()
        self.leaderboard.read_if_changed()
        self.orderbook.poll()
        slug = self._current_slug()

        instance, position, equity, equity_series = self.instance_snapshot(instance_id)
        lb_row = self.leaderboard.row(instance_id)

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
        window = compute_window(slug)

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
            shared_config=self.shared_config(),
            series_up=self._scope_series(
                self.polymarket.series("UP") or self.orderbook.series("UP"), slug
            ),
            series_down=self._scope_series(
                self.polymarket.series("DOWN") or self.orderbook.series("DOWN"), slug
            ),
            model_up=self._scope_series(
                self.docker_log.model_series("UP") or self.terminal.model_series("UP"), slug
            ),
            model_down=self._scope_series(
                self.docker_log.model_series("DOWN") or self.terminal.model_series("DOWN"), slug
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
        lb_row = self.leaderboard.row(instance_id)
        return self._edges_from(terminal, lb_row)

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
