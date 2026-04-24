import json
import os

import pytest

from app.collector.terminal_reader import TerminalReader
from app.config import settings


def _write_terminal(path, timestamp, mtime, timing):
    path.write_text(
        json.dumps(
            {
                "timestamp": timestamp,
                "market_slug": "btc-updown-15m-1770000000",
                "ssvi_surface": {
                    "prob_above": 0.61,
                    "prob_below": 0.39,
                },
                "timing": timing,
            }
        ),
        encoding="utf-8",
    )
    os.utime(path, (mtime, mtime))


def test_terminal_reader_derives_gap_without_carrying_source(tmp_path):
    path = tmp_path / "terminal_data.json"
    reader = TerminalReader(path)

    _write_terminal(
        path,
        "2026-04-23T10:00:00+00:00",
        1_777_000_000,
        {"calibration_s": 2.0, "used_source": "local_offload"},
    )
    first = reader.read_if_changed()
    assert first is not None
    assert first.timing.used_source == "local_offload"
    assert first.timing.used_gap_s is None

    _write_terminal(
        path,
        "2026-04-23T10:00:07.500000+00:00",
        1_777_000_008,
        {"calibration_s": 2.1},
    )
    second = reader.read_if_changed()

    assert second is not None
    assert second.timing.used_source is None
    assert second.timing.used_gap_s == pytest.approx(7.5)


def test_terminal_reader_ignores_local_grid_payload_when_vps_live(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "mode", "live")
    monkeypatch.setattr(settings, "results_dir", tmp_path)
    monkeypatch.setattr(
        TerminalReader,
        "_read_remote_vps_terminal",
        lambda self, *, force=False: None,
    )
    (tmp_path / ".live_location").write_text("vps:infos", encoding="utf-8")

    path = tmp_path / "terminal_data.json"
    reader = TerminalReader(path)

    _write_terminal(
        path,
        "2026-04-23T10:00:00+00:00",
        1_777_000_000,
        {"calibration_s": 2.0, "used_source": "local_offload", "used_gap_s": 8.5},
    )
    first = reader.read_if_changed()
    assert first is not None
    assert first.timing.used_source == "local_offload"
    assert first.timing.used_gap_s == pytest.approx(8.5)

    _write_terminal(
        path,
        "2026-04-23T10:00:07+00:00",
        1_777_000_007,
        {"calibration_s": 2.1},
    )
    assert reader.read_if_changed() is None
    assert reader.latest is first


def test_terminal_reader_uses_remote_payload_when_vps_live_local_grid_races(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(settings, "mode", "live")
    monkeypatch.setattr(settings, "results_dir", tmp_path)
    (tmp_path / ".live_location").write_text("vps:infos", encoding="utf-8")

    remote_payload = {
        "timestamp": "2026-04-23T10:00:08+00:00",
        "market_slug": "btc-updown-15m-1770000000",
        "ssvi_surface": {
            "prob_above": 0.63,
            "prob_below": 0.37,
        },
        "timing": {
            "calibration_s": 2.2,
            "used_source": "vps_local",
            "used_gap_s": 6.5,
        },
    }
    monkeypatch.setattr(
        TerminalReader,
        "_read_remote_vps_terminal",
        lambda self, *, force=False: remote_payload,
    )

    path = tmp_path / "terminal_data.json"
    reader = TerminalReader(path)
    _write_terminal(
        path,
        "2026-04-23T10:00:07+00:00",
        1_777_000_007,
        {"calibration_s": 2.1},
    )

    snap = reader.read_if_changed()

    assert snap is not None
    assert snap.timestamp == "2026-04-23T10:00:08+00:00"
    assert snap.timing.used_source == "vps_local"
    assert snap.timing.used_gap_s == pytest.approx(6.5)
