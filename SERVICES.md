# Service Control - Dashboard + BTC_pricer_15m

All orchestration goes through `python .\manage.py` from this dashboard folder:

| Command | What it does |
|---|---|
| `python .\manage.py start` | Starts the BTC_pricer_15m paper grid and hidden dashboard backend/frontend processes. |
| `python .\manage.py start --no-grid` | Starts only the hidden dashboard backend/frontend processes. |
| `python .\manage.py stop` | Stops dashboard backend/frontend and the paper grid. It does not touch live trading. |
| `python .\manage.py stop --no-grid` | Stops only the dashboard backend/frontend processes. |
| `python .\manage.py restart` | Runs stop, waits 2 seconds, then starts again. |
| `python .\manage.py restart --no-grid` | Restarts only the dashboard backend/frontend processes. |
| `python .\manage.py status` | Shows dashboard ports, grid container status, and live-switch status. |
| `python .\manage.py live status` | Shows where the live trader is running. Also auto-heals a stale VPS sync loop. |
| `python .\manage.py live local` | Starts or restarts local live trading and marks the dashboard as local. |
| `python .\manage.py live vps` | Moves live trading to the Ireland VPS profile in `vps_infos/infos.txt`. |
| `python .\manage.py live vps <profile>` | Moves live trading to a specific VPS profile in `vps_infos/<profile>.txt`. |
| `python .\manage.py live heal` | Restart the VPS → local state-sync loop if it died silently. Idempotent. |
| `python .\manage.py live stop` | Stops all live trading (local + VPS) and marks it stopped. |
| `python .\manage.py setup-vps` | Provisions/deploys the configured VPS before the first switch. |

The old US East VPS was deleted; the current remote live target is the Ireland profile in `vps_infos/infos.txt`.

## What Each Side Is

- `btc_pricer_15m_grid` - 864-instance paper grid. Writes `results/state_snapshot.json` and `results/trades.csv`.
- `btc_pricer_15m_live` - single real-money instance. Writes `results/15m_live_state.json`, `results/15m_live_trades.csv`, and `results/15m_live_equity.csv`.
- `btc_pricer_15m_offload` - local calibration offload. Runs only while live is on the VPS; pushes local probability calculations into the VPS `results/calibration_inbox/` so the VPS live trader's hybrid calibration broker can use both local and remote signals.
- Dashboard backend - FastAPI on `:8799`. Selects state files based on `MODE` in `.env`.
- Dashboard frontend - Vite on `:5174`.

Open the UI at <http://127.0.0.1:5174>.

Dashboard backend/frontend logs are written under `logs/`, and their PIDs are
tracked under `runtime/`. Closing the terminal used to run `python .\manage.py start`
does not stop the dashboard; use `python .\manage.py stop` when you want to shut it down.

## Common Tasks

Switch the dashboard between live and dry-run views by editing `.env`:

```env
MODE=live
# or
MODE=dry_run
```

Then run:

```powershell
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
python .\manage.py live local
python .\manage.py live status
```

Provision or refresh the Ireland VPS, then move live trading there:

```powershell
python .\manage.py setup-vps
python .\manage.py live vps
python .\manage.py live status
```

When live is on the VPS, the switcher also starts `btc_pricer_15m_offload`
locally. That container sends local probability calculations into the VPS
`results/calibration_inbox/`; the VPS live trader also calculates locally and
uses its hybrid calibration broker to consume both sources safely.

A detached Python sync loop (`live_manager.py --sync-loop <profile>`) mirrors
the VPS `results/` tree down to the local `results/` so the dashboard always
reads fresh live state. The loop writes its heartbeat to
`results/.vps_sync_last`. If the loop ever dies silently, the next
`python .\manage.py live status` or `live heal` call restarts it automatically.

Stop all live trading:

```powershell
python .\manage.py live stop
python .\manage.py live status
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
- Backend shows the wrong mode after editing `.env`: run `python .\manage.py restart`.
- Dashboard says remote/local incorrectly after a live switch: run `python .\manage.py live status`, then reload the browser after the backend pushes the next liveness update.
- To switch back from the Ireland VPS, run `python .\manage.py live local`; it stops remote live, pulls final state, and starts local live.
- Sync heartbeat drifts (>30s old) while on VPS: run `python .\manage.py live status` (or `live heal`) — the auto-heal path will restart the loop.
