import json
from pathlib import Path

import pytest

from app.collector.state_reader import StateReader, instance_from_raw, position_from_raw


def test_instance_stats_derivation():
    raw = {
        "capital": 1200.0,
        "total_pnl": 200.0,
        "wins": 8,
        "losses": 2,
        "trades_count": 10,
        "trade_pnls": [10, -5, 20, -10, 30, -5, 50, -10, 60, 60],
    }
    s = instance_from_raw(773, raw, starting_capital=1000.0)
    assert s.instance_id == 773
    assert s.capital == 1200.0
    assert s.total_pnl == 200.0
    assert s.wins == 8 and s.losses == 2 and s.trades_count == 10
    assert s.win_rate == 80.0
    assert s.sharpe > 0
    assert s.max_drawdown >= 0


def test_max_drawdown_pct_uses_running_peak():
    raw = {
        "capital": 1100.0,
        "trade_pnls": [1500.0, -1400.0],
    }
    s = instance_from_raw(773, raw, starting_capital=1000.0)
    assert s.max_drawdown == pytest.approx(1400.0)
    assert s.max_drawdown_pct == pytest.approx(56.0, abs=0.01)
    assert s.max_drawdown_pct <= 100.0


def test_instance_stats_respect_explicit_starting_capital():
    raw = {
        "capital": 120.0,
        "trade_pnls": [20.0],
    }
    s = instance_from_raw(773, raw, starting_capital=100.0)
    assert s.starting_capital == 100.0
    assert s.total_pnl == 20.0
    assert s.total_pnl_pct == 20.0


def test_position_from_raw_flat():
    assert position_from_raw({"position": None, "last_tp_sl_time": "2026-04-20T10:00:00+00:00"}).open is None


def test_position_from_raw_open():
    raw = {
        "position": {
            "direction": "UP",
            "entry_price": 0.64,
            "shares": 4.6,
            "tp_price": 0.736,
            "stop_loss_price": 0.0,
            "opened_at": "2026-04-20T14:50:17+00:00",
            "market_id": "btc-updown-15m-1776696300",
            "cost_basis": 3.0,
        },
    }
    ps = position_from_raw(raw)
    assert ps.open is not None
    assert ps.open.direction == "UP"
    assert ps.open.shares == 4.6
    assert ps.open.market_id.startswith("btc-updown-15m")


def test_state_reader_diff_by_mtime(tmp_path: Path):
    p = tmp_path / "state.json"
    p.write_text(json.dumps({"instances": {"773": {"capital": 1100.0, "total_pnl": 100.0, "trade_pnls": []}}}))
    r = StateReader(path_fn=lambda: p)
    assert r.read_if_changed() is True
    assert r.read_if_changed() is False
    stats = r.instance(773)
    assert stats is not None
    assert stats.capital == 1100.0


def test_state_reader_instance_uses_supplied_starting_capital(tmp_path: Path):
    p = tmp_path / "state.json"
    p.write_text(json.dumps({"instances": {"773": {"capital": 110.0, "trade_pnls": [10.0]}}}))
    r = StateReader(path_fn=lambda: p)
    assert r.read_if_changed() is True
    stats = r.instance(773, starting_capital=100.0)
    assert stats is not None
    assert stats.starting_capital == 100.0
    assert stats.total_pnl == 10.0
    assert stats.total_pnl_pct == 10.0
