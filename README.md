# Polymarket Streaming Dashboard

Real-time dashboard for the `BTC_pricer_15m` Polymarket bot running in Docker. Shows, for any
chosen dry-run parameter set (default: leaderboard rank 7, instance `#773` — `aU=2.5 aD=1.8
fU=0.45 fD=0.65 tp=0.3 sl=0.2`):

- Model probabilities — SSVI surface (BL-style), SSVI + Monte Carlo, Heston if computed, and
  the average — both UP and DOWN.
- Polymarket market-implied probabilities (from the CLOB mid).
- **Current edge ratio** and the **required edge ratio** for the instance's α/floor, with margin.
- Current market info: spot, barrier, direction, TTM.
- 15-min window timer with blocked/tradeable zones.
- Position state (flat / open, entry, TP/SL) and a live-trading grace-period badge.
- Instance performance: capital, PnL, Sharpe, max DD, win rate, rank, equity curve.
- Trade feed with animated entry/win/loss bursts.
- Leaderboard top 15 — click to focus a different instance.
- "Calculating new calibration…" indicator when a SSVI/MC cycle is running.

Locked to a 16:9 frame for clean OBS capture at 1920×1080.

## Prerequisites

- The bot in `../BTC_pricer_15m/` is running (Docker `btc_pricer_15m_grid` or otherwise)
  and producing files under `results/` (`state_snapshot.json`, `trades.csv`, `terminal_data.json`,
  `leaderboard.csv`, `15m_orderbook.csv`, `trader.lock`).
- Python 3.10+ and Node 20+.

## Quick start

```bash
# 1. Backend
cd backend
python -m pip install fastapi "uvicorn[standard]" pydantic pydantic-settings python-dotenv
cp ../.env.example .env   # default paths assume sibling ../BTC_pricer_15m

# 2. Frontend
cd ../frontend
npm install

# 3. Run both (from project root)
./scripts/run_dev.sh
```

- Backend: http://127.0.0.1:8799 (`/api/bootstrap`, `/api/instances`, `/ws`)
- Frontend: http://127.0.0.1:5174

The dev script uses ports **8799** and **5174** to avoid clashing with the sibling
`STREAMING_LIVE_PASSIBOT` dashboard (8787 / 5173).

## Production / OBS capture

```bash
./scripts/run_prod.sh
```

Builds `frontend/` to `frontend/dist/`, then launches uvicorn which serves the static bundle
and API together on http://127.0.0.1:8799.

## Switching to live mode

```bash
# In .env
MODE=live
```

The backend then reads `results/15m_live_state.json` and `results/15m_live_trades.csv`
(and applies `grace_period_seconds` from `config_trader_live.json` to the grace-period pill).
The leaderboard and instance selector hide themselves in live mode since there is only one
parameter set.

## Tests

```bash
cd backend
python -m pytest tests/ -q
```

## Architecture (tl;dr)

- **Read-only**: the dashboard *never* writes inside `BTC_pricer_15m/results/`.
- Backend polls bot state files (file-mtime diffing and byte-offset CSV tailing), publishes
  typed events on an in-process `EventBus`, and streams them to the browser via WebSocket
  envelopes. Bootstrap state is served via HTTP.
- Frontend is React + Vite + Tailwind + Zustand, with recharts for sparklines and framer-motion
  for entry/exit/calibration animations.

## Files touched in the bot's project

**None.** This dashboard only reads; it does not modify the bot, its config, or its `results/`.
