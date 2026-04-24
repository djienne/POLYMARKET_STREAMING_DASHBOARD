# Service Control - Dashboard + BTC_pricer_15m

Use the Python manager from this dashboard folder on Windows:

| Command | What it does |
|---|---|
| `python .\manage.py start` | Starts the BTC_pricer_15m paper grid and hidden dashboard backend/frontend processes. |
| `python .\manage.py start --no-grid` | Starts only the hidden dashboard backend/frontend processes. |
| `python .\manage.py stop` | Stops dashboard backend/frontend and the paper grid. It does not touch live trading. |
| `python .\manage.py stop --no-grid` | Stops only the dashboard backend/frontend processes. |
| `python .\manage.py restart` | Runs stop, waits 2 seconds, then starts again. |
| `python .\manage.py restart --no-grid` | Restarts only the dashboard backend/frontend processes. |
| `python .\manage.py status` | Shows dashboard ports, grid container status, and live-switch status. |
| `python .\manage.py live status` | Shows where the live trader is running. |
| `python .\manage.py live local` | Starts or restarts local live trading and marks the dashboard as local. |
| `python .\manage.py live vps` | Moves live trading to the Ireland VPS profile in `vps_infos/infos.txt`. |
| `python .\manage.py live stop` | Stops local live trading and marks it stopped. |
| `python .\manage.py setup-vps` | Provisions/deploys the configured VPS before the first switch. |

The PowerShell scripts are thin compatibility wrappers around `manage.py`:

| Script | What it does |
|---|---|
| `.\start.ps1` | Calls `python .\manage.py start`. |
| `.\stop.ps1` | Calls `python .\manage.py stop`. |
| `.\restart.ps1` | Calls `python .\manage.py restart`. |
| `.\status.ps1` | Calls `python .\manage.py status`. |
| `.\live_switch.ps1 ...` | Calls `python .\manage.py live ...`. |
| `.\setup_vps.ps1` | Calls `python .\manage.py setup-vps`. |

The `.bat` scripts, including `status.bat`, are Explorer-friendly wrappers around the same Python manager. The old US East VPS was deleted; the current remote live target is the Ireland profile in `vps_infos/infos.txt`.

## What Each Side Is

- `btc_pricer_15m_grid` - 864-instance paper grid. Writes `results/state_snapshot.json` and `results/trades.csv`.
- `btc_pricer_15m_live` - single real-money instance. Writes `results/15m_live_state.json`, `results/15m_live_trades.csv`, and `results/15m_live_equity.csv`.
- Dashboard backend - FastAPI on `:8799`. Selects state files based on `MODE` in `.env`.
- Dashboard frontend - Vite on `:5174`.

Open the UI at <http://127.0.0.1:5174>.

Dashboard backend/frontend logs are written under `logs/`, and their PIDs are
tracked under `runtime/`. Closing the terminal used to run `manage.py start` or
`start.ps1` does not stop the dashboard; use `python .\manage.py stop` when you
want to shut it down.

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
# or:
python .\manage.py restart
```

Use `python .\manage.py restart --no-grid` when you only changed dashboard code
or `.env` and do not want to touch the 864-instance paper grid.

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
# or:
python .\manage.py live local
python .\manage.py live status
```

Provision or refresh the Ireland VPS, then move live trading there:

```powershell
.\setup_vps.ps1
.\live_switch.ps1 vps
.\live_switch.ps1 status
# or:
python .\manage.py setup-vps
python .\manage.py live vps
python .\manage.py live status
```

When live is on the VPS, the switcher also starts `btc_pricer_15m_offload`
locally. That container sends local probability calculations into the VPS
`results/calibration_inbox/`; the VPS live trader also calculates locally and
uses its hybrid calibration broker to consume both sources safely.

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

- Dashboard does not open: check `logs/dashboard_backend.err.log` and `logs/dashboard_frontend.err.log`, then run `python .\manage.py restart`.
- `docker` not found: make sure Docker Desktop is running and available from Windows PowerShell.
- Backend shows the wrong mode after editing `.env`: run `.\restart.ps1`.
- Dashboard says remote/local incorrectly after a live switch: run `.\live_switch.ps1 status`, then reload the browser after the backend pushes the next liveness update.
- To switch back from the Ireland VPS, run `.\live_switch.ps1 local`; it stops remote live, pulls final state, and starts local live.
