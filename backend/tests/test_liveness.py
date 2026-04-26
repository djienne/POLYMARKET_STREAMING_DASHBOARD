from pathlib import Path

from app.collector.liveness import _active_lock_exists, _active_lock_paths
from app.config import settings


def test_live_liveness_accepts_single_trader_lock(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(settings, "mode", "live")
    monkeypatch.setattr(settings, "results_dir", tmp_path)

    (tmp_path / "single_trader.lock").write_text("pid", encoding="utf-8")

    assert _active_lock_paths()[0] == tmp_path / "single_trader.lock"
    assert _active_lock_exists() is True


def test_dry_run_liveness_uses_grid_lock(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(settings, "mode", "dry_run")
    monkeypatch.setattr(settings, "results_dir", tmp_path)

    (tmp_path / "trader.lock").write_text("pid", encoding="utf-8")

    assert _active_lock_paths() == [tmp_path / "trader.lock"]
    assert _active_lock_exists() is True
