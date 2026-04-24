import json
from pathlib import Path

import pytest

import live_manager
from manage import VpsProfile


def _profile() -> VpsProfile:
    return VpsProfile(
        name="test",
        label="Test VPS",
        host="127.0.0.1",
        user="ubuntu",
        directory="/remote/app",
        key=Path("dummy.pem"),
    )


def _state(count: int) -> bytes:
    return json.dumps({"closed_positions": [{"id": str(i)} for i in range(count)]}).encode()


def test_optional_history_missing_on_vps_preserves_local_file(tmp_path, monkeypatch):
    monkeypatch.setattr(live_manager, "RESULTS_DIR", tmp_path)
    local = tmp_path / "15m_live_trades.csv"
    local.write_text("id,pnl\nold,1\n", encoding="utf-8")
    monkeypatch.setattr(live_manager, "_ssh_cat", lambda profile, path: (44, b""))

    assert live_manager._pull_one_file(_profile(), "15m_live_trades.csv", required=False)

    assert local.read_text(encoding="utf-8") == "id,pnl\nold,1\n"


def test_pull_refuses_to_replace_richer_local_state_with_empty_remote(tmp_path, monkeypatch):
    monkeypatch.setattr(live_manager, "RESULTS_DIR", tmp_path)
    local = tmp_path / "15m_live_state.json"
    local.write_bytes(_state(3))
    monkeypatch.setattr(live_manager, "_ssh_cat", lambda profile, path: (0, _state(0)))

    assert live_manager._pull_one_file(_profile(), "15m_live_state.json", required=True)

    assert live_manager._closed_position_count_from_file(local) == 3


def test_required_state_missing_on_vps_preserves_local_file(tmp_path, monkeypatch):
    monkeypatch.setattr(live_manager, "RESULTS_DIR", tmp_path)
    local = tmp_path / "15m_live_state.json"
    local.write_bytes(_state(3))
    monkeypatch.setattr(live_manager, "_ssh_cat", lambda profile, path: (44, b""))

    assert not live_manager._pull_one_file(_profile(), "15m_live_state.json", required=True)

    assert live_manager._closed_position_count_from_file(local) == 3


def test_push_refuses_to_replace_richer_vps_state_with_empty_local(tmp_path, monkeypatch):
    monkeypatch.setattr(live_manager, "RESULTS_DIR", tmp_path)
    (tmp_path / "15m_live_state.json").write_bytes(_state(0))
    monkeypatch.setattr(live_manager, "_remote_closed_position_count", lambda profile: 3)

    with pytest.raises(RuntimeError, match="refusing to replace VPS live history"):
        live_manager._guard_against_history_regression(
            _profile(),
            source="local",
            target="VPS",
        )


def test_live_history_backup_copies_state_trade_and_equity_files(tmp_path, monkeypatch):
    monkeypatch.setattr(live_manager, "RESULTS_DIR", tmp_path)
    backup_dir = tmp_path / "live_history_backups"
    monkeypatch.setattr(live_manager, "LIVE_HISTORY_BACKUP_DIR", backup_dir)
    for name in live_manager.LIVE_HISTORY_FILES:
        (tmp_path / name).write_text(f"{name}\n", encoding="utf-8")

    created = live_manager.backup_live_history("unit_test")

    assert created is not None
    for name in live_manager.LIVE_HISTORY_FILES:
        assert (created / name).read_text(encoding="utf-8") == f"{name}\n"
