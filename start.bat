@echo off
REM start.bat - start the BTC_pricer_15m paper grid and the dashboard.
REM Live trading is controlled only by live_switch.ps1.

setlocal

echo [start] docker compose up -d grid ...
pushd "%~dp0..\BTC_pricer_15m"
docker compose up -d grid
popd

echo [start] launching backend uvicorn on :8799 ...
pushd "%~dp0backend"
start "Dashboard Backend (uvicorn :8799)" /MIN cmd /c "python -m uvicorn app.main:app --host 127.0.0.1 --port 8799 --reload"
popd

echo [start] launching frontend vite on :5174 ...
pushd "%~dp0frontend"
start "Dashboard Frontend (vite :5174)" /MIN cmd /c "npm run dev"
popd

echo [start] done. Dashboard: http://127.0.0.1:5174  (backend API: :8799)
endlocal
