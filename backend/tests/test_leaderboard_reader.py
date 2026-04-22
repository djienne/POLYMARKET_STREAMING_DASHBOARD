from pathlib import Path

from app.collector.leaderboard_reader import LeaderboardReader


HEADER = "rank,instance_id,total_pnl,sharpe,max_drawdown,max_drawdown_pct,wins,losses,win_rate,trades,alpha_up,alpha_down,floor_up,floor_down,tp_pct,sl_pct,liquidity_mode\n"
ROW = "1,773,12.5,1.2,3.4,5.6,7,1,87.5,8,2.5,1.8,0.45,0.45,0.3,0.0,independent\n"


def test_leaderboard_reader_preserves_last_good_snapshot_on_read_error(tmp_path: Path, monkeypatch):
    p = tmp_path / "leaderboard.csv"
    p.write_text(HEADER + ROW)
    reader = LeaderboardReader(path_fn=lambda: p)
    assert reader.read_if_changed() is True
    assert len(reader.rows) == 1

    from app.collector import leaderboard_reader as mod

    def _boom(_path: Path):
        raise OSError("sharing violation")

    p.write_text(HEADER + ROW)
    monkeypatch.setattr(mod, "parse_leaderboard", _boom)
    assert reader.read_if_changed() is False
    assert len(reader.rows) == 1
    assert reader.row(773) is not None
