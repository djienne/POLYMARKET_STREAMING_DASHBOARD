# Service Control - Dashboard + BTC_pricer_15m

Use the PowerShell scripts from this dashboard folder on Windows:

| Script | What it does |
|---|---|
| `.\start.ps1` | Starts the BTC_pricer_15m paper grid and dashboard backend/frontend. |
| `.\stop.ps1` | Stops dashboard backend/frontend and the paper grid. It does not touch live trading. |
| `.\restart.ps1` | Runs `stop.ps1`, waits 2 seconds, then runs `start.ps1`. |
| `.\status.ps1` | Shows dashboard ports, grid container status, and live-switch status. |
| `.\live_switch.ps1 status` | Shows where the live trader is running. |
| `.\live_switch.ps1 local` | Starts or restarts local live trading and marks the dashboard as local. |
| `.\live_switch.ps1 stop` | Stops local live trading and marks it stopped. |

The `.bat` scripts remain as Explorer-friendly wrappers for dashboard/grid only. The old US East VPS has been deleted, so the active live switch is now local-only.

## What Each Side Is

- `btc_pricer_15m_grid` - 864-instance paper grid. Writes `results/state_snapshot.json` and `results/trades.csv`.
- `btc_pricer_15m_live` - single real-money instance. Writes `results/15m_live_state.json`, `results/15m_live_trades.csv`, and `results/15m_live_equity.csv`.
- Dashboard backend - FastAPI on `:8799`. Selects state files based on `MODE` in `.env`.
- Dashboard frontend - Vite on `:5174`.

Open the UI at <http://127.0.0.1:5174>.

## Common Tasks

Switch the dashboard between live and dry-run views by editing `.env`:

```env
MODE=live
# or
MODE=dry_run
```

Then run:

```powershell
.\restart.ps1
```

Check container health:

```powershell
docker ps --filter name=btc_pricer_15m
docker logs --tail 50 btc_pricer_15m_grid
docker logs --tail 50 btc_pricer_15m_live
```

Start or restart the live trader locally:

```powershell
.\live_switch.ps1 local
.\live_switch.ps1 status
```

Stop the local live trader:

```powershell
.\live_switch.ps1 stop
.\live_switch.ps1 status
```

## State-File Safety

Never delete:

- `../BTC_pricer_15m/results/trades.csv`
- `../BTC_pricer_15m/results/state_snapshot.json`
- `../BTC_pricer_15m/results/15m_live_state.json`
- `../BTC_pricer_15m/results/15m_live_trades.csv`
- `../BTC_pricer_15m/results/15m_live_equity.csv`

Only `../BTC_pricer_15m/results/trader.lock` is safe to remove if it got stale from a hard kill.

## Troubleshooting

- Dashboard windows open but exit immediately: something else is on `:8799` or `:5174`. Run `.\stop.ps1`, then `.\start.ps1`.
- `docker` not found: make sure Docker Desktop is running and available from Windows PowerShell.
- Backend shows the wrong mode after editing `.env`: run `.\restart.ps1`.
- Dashboard says remote/local incorrectly after a live switch: run `.\live_switch.ps1 status`, then reload the browser after the backend pushes the next liveness update.
- `.\live_switch.ps1 vps us_east` fails by design: the US East VPS was deleted.
