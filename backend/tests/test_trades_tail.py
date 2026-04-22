import time
from pathlib import Path

from app.collector.trades_tail import TradesTail


HEADER = "instance_id,timestamp,event,direction,market_id,entry_price,exit_price,shares,pnl,pnl_pct,capital,model_prob,poly_prob,spot_price,barrier\n"


def _row(iid, event, pnl=""):
    return f"{iid},2026-04-20T10:00:00+00:00,{event},UP,slug,0.5,,10,{pnl},,1000,0.6,0.5,70000,70100\n"


def test_tail_picks_up_appended_rows(tmp_path: Path):
    p = tmp_path / "trades.csv"
    p.write_text(HEADER + _row(773, "ENTRY"))
    t = TradesTail(path_fn=lambda: p)
    assert len(t.seed()) == 1
    assert t.recent(773)[0].event == "ENTRY"

    with p.open("a") as f:
        f.write(_row(773, "TP_FILLED", "5.00"))
    new = t.poll()
    assert len(new) == 1
    assert new[0].event == "TP_FILLED"
    assert new[0].pnl == 5.00
    # Newest-first recent list
    r = t.recent(773, 5)
    assert r[0].event == "TP_FILLED"
    assert r[1].event == "ENTRY"


def test_tail_ignores_partial_line(tmp_path: Path):
    p = tmp_path / "trades.csv"
    p.write_text(HEADER + _row(773, "ENTRY"))
    t = TradesTail(path_fn=lambda: p)
    t.seed()
    # Append a partial line (no newline yet)
    with p.open("a") as f:
        f.write("773,2026-04-20T10:01:00+00:00,TP_FILLED,UP,slug,0.5,,10,1.00")
    new = t.poll()
    assert new == []
    # Complete the line
    with p.open("a") as f:
        f.write(",,1001,0.6,0.5,70000,70100\n")
    new = t.poll()
    assert len(new) == 1
    assert new[0].event == "TP_FILLED"


def test_tail_scoped_by_instance(tmp_path: Path):
    p = tmp_path / "trades.csv"
    p.write_text(HEADER + _row(773, "ENTRY") + _row(100, "ENTRY"))
    t = TradesTail(path_fn=lambda: p)
    t.seed()
    assert len(t.recent(773)) == 1
    assert len(t.recent(100)) == 1
    assert t.recent(999) == []


def test_realized_history_keeps_full_close_history(tmp_path: Path):
    p = tmp_path / "trades.csv"
    rows = "".join(_row(773, "TP_FILLED", "1.00") for _ in range(205))
    p.write_text(HEADER + rows)
    t = TradesTail(path_fn=lambda: p)
    t.seed()
    assert len(t.recent(773, 300)) == 200
    assert len(t.realized_history(773)) == 205


def test_realized_history_includes_unresolved_restart(tmp_path: Path):
    p = tmp_path / "trades.csv"
    p.write_text(HEADER + _row(773, "UNRESOLVED_RESTART"))
    t = TradesTail(path_fn=lambda: p)
    t.seed()
    history = t.realized_history(773)
    assert len(history) == 1
    assert history[0].event == "UNRESOLVED_RESTART"


def test_today_summary_uses_full_day_history(tmp_path: Path):
    p = tmp_path / "trades.csv"
    rows = [
        "773,2026-04-22T08:00:00+00:00,ENTRY,UP,slug,0.5,,10,,,,70000,70100\n",
        "773,2026-04-22T08:01:00+00:00,TP_FILLED,UP,slug,0.5,0.8,10,3.00,,1003,0.6,0.5,70000,70100\n",
        "773,2026-04-22T08:02:00+00:00,ENTRY,DOWN,slug,0.5,,10,,,,70000,70100\n",
        "773,2026-04-22T08:03:00+00:00,STOP_LOSS,DOWN,slug,0.5,0.2,10,-2.00,,1001,0.4,0.5,70000,70100\n",
    ]
    p.write_text(HEADER + "".join(rows))
    t = TradesTail(path_fn=lambda: p)
    t.seed()
    summary = t.today_summary(773, "2026-04-22")
    assert summary.entries == 2
    assert summary.closed == 2
    assert summary.wins == 1
    assert summary.losses == 1
    assert summary.pnl == 1.0
