import json
import os

import pytest

from app.collector.terminal_reader import TerminalReader


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
