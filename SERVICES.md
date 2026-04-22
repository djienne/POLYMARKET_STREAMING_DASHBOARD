# Service control — Dashboard + BTC_pricer_15m

Three `.bat` scripts in this folder control **both** stacks together:

| Script | What it does |
|---|---|
| `start.bat`   | Starts BTC_pricer_15m containers (`grid` + `live`) and the dashboard (uvicorn `:8799` + vite `:5174`). |
| `stop.bat`    | Kills dashboard processes bound to `:8799` / `:5174` and runs `docker compose down` in `../BTC_pricer_15m`. |
| `restart.bat` | `stop.bat` → 2s delay → `start.bat`. |

Double-click any of them in Explorer, or run from a shell.

## What each side is

- **`btc_pricer_15m_grid`** — 864-instance paper grid (dry runs). Writes `results/state_snapshot.json` and `results/trades.csv`.
- **`btc_pricer_15m_live`** — single real-money instance running `aU=2.5 aD=1.8 fU=0.45 fD=0.45 tp=0.3`. Writes `results/15m_live_state.json`, `results/15m_live_trades.csv`, `results/15m_live_equity.csv`. Capital pulled from on-chain USDC at `0xb3DdA27Bd7Cac44d92479F4000a40b9dF4955CCd`.
- **Dashboard backend** — FastAPI on `:8799`. Selects which state file to read based on `MODE` in `.env` (`live` → `15m_live_state.json`, `dry_run` → `state_snapshot.json`).
- **Dashboard frontend** — Vite on `:5174`. LIVE badge + Polymarket profile chip appear when `MODE=live`. Equity Y-axis auto-scales to `starting_capital` (≈ $100 live, $1000 paper).

Open the UI at <http://127.0.0.1:5174>.

## Common tasks

**Switch the dashboard between live and dry-run views**

Edit `.env`:
```env
MODE=live      # or: MODE=dry_run
```
Then `restart.bat` (only the backend needs a reload, but restarting both is simplest).

**Check container health**

```bash
docker ps --filter name=btc_pricer_15m
docker logs -f btc_pricer_15m_live
docker logs --tail 50 btc_pricer_15m_grid
```

**Verify the live trader auto-detected starting capital**

First lines of `docker logs btc_pricer_15m_live` should show:
```
Live USDC balance: $<balance>
Starting Capital: $100.00
Mode: LIVE
Edge curve: UP alpha=2.5 floor=45% | DOWN alpha=1.8 floor=45%
TP target: 30%
```

**Change live-run parameters**

Edit `../BTC_pricer_15m/config_trader_live.json`, then `restart.bat`. The config is bind-mounted, so `docker compose up -d` without rebuild is enough — but `restart.bat` rebuilds nothing and just restarts containers, which is what you want.

If you edit **Python code** under `BTC_pricer_15m/scripts/`, you need a rebuild:
```bash
cd ../BTC_pricer_15m
docker compose build
docker compose up -d
```
(or call `restart.bat` after doing `docker compose build` manually).

## State-file safety

Never delete:
- `../BTC_pricer_15m/results/trades.csv`
- `../BTC_pricer_15m/results/state_snapshot.json`
- `../BTC_pricer_15m/results/15m_live_state.json`
- `../BTC_pricer_15m/results/15m_live_trades.csv`

Only `../BTC_pricer_15m/results/trader.lock` is safe to remove if it got stale from a hard kill.

## Troubleshooting

- **Dashboard windows open but exit immediately**: something else is on `:8799` or `:5174`. Run `stop.bat` first, then `start.bat`.
- **`docker compose` not found**: make sure Docker Desktop is running.
- **Backend shows DRY-RUN even after setting `MODE=live`**: backend reads `.env` at startup. `restart.bat` picks it up.
- **Equity curve empty**: `results/15m_live_equity.csv` may not have ticks yet. The live trader writes it each tick (`~5s`). Reload the page after ~30s.
